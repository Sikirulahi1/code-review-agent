# **AI Code Review Agent  Full System Architecture**

**Author:** Abdulkareem Sikirulahi **Version:** 3.0 **Date:** April 2026

## **1\. Executive Summary**

The AI Code Review Agent is an automated system that integrates directly with GitHub to provide intelligent, multi-dimensional analysis of every pull request. When a developer opens or updates a PR, the system is triggered via a GitHub webhook, fetches the code diff, and routes it through a LangGraph-powered multi-agent pipeline where specialized agents each examine a distinct quality dimension, bugs, security, performance, and code style.

Each agent produces structured findings with severity levels, confidence scores, and line-level references. A supervisor agent then aggregates, deduplicates, and formats these into actionable inline comments posted directly onto the PR via the GitHub API. Before any comment is posted, every finding passes through a diff position mapping engine that validates whether the finding can be posted inline on GitHub at all  findings that cannot be routed to a PR-level summary comment instead of being silently dropped. The system tracks findings across PR updates using stable fingerprints so it never re-posts comments on issues a developer has already fixed. The result is the equivalent of a senior engineer code review  available instantly, on every PR, at any hour, and smart enough to follow the conversation as the PR evolves.

The primary LLM is Google Gemini (gemini-2.5-pro). OpenAI GPT-4o serves as the fallback in the event of Gemini API failures or rate limits.

## **2\. System Overview**

### **2.1 The Core Problem**

Manual code reviews are slow, inconsistent, and expensive. Developers wait hours for feedback, reviewers miss issues under time pressure, and common problems like security vulnerabilities or performance anti-patterns get through. The AI Code Review Agent solves this by providing a consistent, thorough first pass on every PR  freeing human reviewers to focus on architecture and logic rather than catching obvious issues.

### **2.2 High-Level Flow**

PR opened/updated on GitHub  
        ↓  
GitHub sends webhook POST to FastAPI server  
        ↓  
Server verifies HMAC-SHA256 signature and extracts PR metadata  
        ↓  
GitHub API fetches PR title, description, and full unified diff  
        ↓  
Coordinator agent parses diff, chunks by file, seeds graph state  
        ↓  
Four specialist agents run in parallel (Gemini / OpenAI fallback)  
        ↓  
Supervisor agent receives all findings \+ PR context  
        ↓  
Supervisor deduplicates, applies confidence filtering, filters against PR intent  
        ↓  
Diff position mapper validates each finding against the unified diff  
        ↓  
Findings with valid positions → inline comments  
Findings with no valid position → summary comment (fallback)  
        ↓  
Fingerprint engine compares findings against previous review stored in Postgres  
        ↓  
Comment engine posts new comments, replies to persisted threads, resolves fixed ones  
        ↓  
All data stored in PostgreSQL for analytics and future review runs

## **3\. Architecture Components**

### **3.1 GitHub Integration Layer**

This layer handles all communication with GitHub in both directions.

**Inbound:** GitHub sends a signed POST request to the `/webhook` endpoint on every `pull_request` and `issue_comment` event. The server verifies the request using HMAC-SHA256 signature validation with the `GITHUB_WEBHOOK_SECRET` to confirm the payload is genuine from GitHub. The `issue_comment` event is also listened for to support the `/review` manual trigger command.

**Outbound:** The PyGithub library wraps the GitHub REST API for all outbound calls. Authentication uses a personal access token or GitHub App credentials stored in environment variables. All outbound comment posting goes through a queue with exponential backoff to handle GitHub's secondary rate limits on write operations gracefully.

Key operations:

* Webhook signature verification on every incoming request  
* Fetching PR metadata (title, description, author) via `GET /repos/{owner}/{repo}/pulls/{pull_number}`  
* Fetching the PR diff via `GET /repos/{owner}/{repo}/pulls/{pull_number}/files`  
* Posting new inline review comments via `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments`  
* Replying to existing comment threads via `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` with `in_reply_to`  
* Resolving outdated comments via the GitHub review comment outdated API  
* Creating a PR-level summary review via `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`  
* Optionally setting commit status checks to block merging on critical findings

**Outbound Rate Limiting:** GitHub enforces secondary rate limits specifically on write operations that are separate from the 5,000 requests per hour primary limit. Silent failures on comment posting are particularly dangerous because the review runs successfully internally but nothing appears on the PR. To prevent this, all comment posting calls in `github_client.py` go through a lightweight in-memory queue with exponential backoff starting at 1 second and capping at 60 seconds. Every failure is logged explicitly. Diff fetches are cached by commit SHA to avoid redundant calls on re-triggered webhooks.

### **3.2 FastAPI Webhook Server**

The FastAPI server is the entry point of the entire system. It exposes endpoints that receive GitHub events, validate payloads, extract metadata, and dispatch review jobs as background tasks so GitHub receives a 200 response immediately without waiting for the full review to complete.

**Endpoints:**

* `POST /webhook`  receives all GitHub events, verifies signature, dispatches review or command handling as a background task  
* `GET /health`  health check for Railway deployment monitoring  
* `GET /reviews/{pr_number}`  retrieve stored review results for a given PR, including whether the latest commit SHA has been reviewed  
* `POST /webhook/test`  accepts mock payloads for local development testing

The `/review` command is handled through the same webhook endpoint. When a developer posts a PR comment containing `/review`, the `issue_comment` event fires, the server recognizes the command, and triggers a fresh full review on demand. This serves as both a manual re-review trigger and a recovery mechanism for missed webhook deliveries caused by server downtime during deployments.

FastAPI was chosen because it is async-native, performs well under concurrent webhook loads, and integrates cleanly with the rest of the Python stack.

### **3.3 LangGraph Multi-Agent Pipeline**

This is the core intelligence of the system. LangGraph orchestrates a directed graph of AI agents where each node is a specialized reviewer. The pipeline uses a hub-and-spoke pattern: a coordinator node preprocesses the diff and PR context, fans out to four specialist agents running in parallel, and then fans back into a supervisor node that assembles the final review.

**Why LangGraph over a simple chain:**

* Parallel execution significantly reduces total review time  
* Graph state is explicit and inspectable, making debugging straightforward  
* Conditional edges allow skipping certain agents based on file types present in the diff  
* Per-node timeouts mean a slow or failing agent never blocks the full pipeline

**LLM Strategy:** All agent calls target Gemini (gemini-2.5-pro) as the primary model. A wrapper function in `llm_client.py` handles the fallback: if a Gemini call fails or times out (30-second timeout), the same prompt is retried once with OpenAI (gpt-4o) before the agent is marked as failed. If both models fail, the agent's findings are set to an empty list, a warning is logged in the graph state error list, and the pipeline continues with remaining agents. No single agent failure blocks the review from completing.

**Agent Roster:**

| Agent | Responsibility | Output |
| ----- | ----- | ----- |
| Coordinator | Parses diff, chunks by file, fetches PR title and description, seeds graph state | Structured diff chunks per file \+ PR context object |
| Bug Detector | Logic errors, null risks, unhandled exceptions, off-by-one errors | Bug findings with line numbers, severity, and confidence |
| Security Scanner | Hardcoded secrets, injection vulnerabilities, auth flaws, unsafe inputs | Security findings with CWE references, severity, and confidence |
| Performance Reviewer | Inefficient loops, N+1 queries, memory leaks, blocking I/O in async code | Performance findings with impact estimates, severity, and confidence |
| Style Checker | Naming conventions, missing docstrings, dead code, cyclomatic complexity | Style findings with auto-fix suggestions, severity, and confidence |
| Supervisor | Receives all findings \+ PR context; deduplicates, applies confidence filtering, filters against PR intent, generates summary | Final structured review payload |

### **3.4 Coordinator Agent  PR Context Handling**

The coordinator fetches the PR title and description from the GitHub API alongside the diff. This context is stored in the graph state but is not passed directly to specialist agents. Agents analyze the diff only. The PR context is passed exclusively to the supervisor, whose prompt instructs it to suppress or downgrade findings that the PR description explains as intentional. This design keeps agents focused on detection while context informs judgment at the aggregation stage, preventing PR context from biasing agents away from flagging real issues that happen to be mentioned in the description.

Full PR comment threads, commit messages, and linked issue bodies are not included at this stage. PR title and description alone is sufficient to catch the most common category of intent-related false positives. Additional context sources will be evaluated after measuring whether this baseline alone brings false positive rates to target levels.

### **3.5 Chunking Strategy**

Each file's diff is treated as an independent unit processed separately. The chunking strategy depends on the file type.

**AST-based chunking** (for supported languages): If a single file's diff exceeds the per-agent token budget (6,000 tokens), it is split at function or class boundaries using a lightweight AST parser to ensure each chunk is semantically coherent. Supported languages for AST chunking: Python, JavaScript, TypeScript.

**Line-count-based chunking** (fallback for all other file types): For files in unsupported formats  including YAML, Terraform HCL, SQL, Go, Rust, and all other formats not in the supported list  the system falls back to simple line-count-based chunking at 400 lines per chunk. This fallback does not produce semantically coherent chunks but it does not crash or fail silently. Which chunking strategy was applied to each file is logged in the graph state and stored in Postgres so production monitoring can track how frequently the fallback fires and which file types trigger it.

Findings from multiple chunks of the same file are merged after processing. Duplicate findings (same file, overlapping line range, same category) are resolved by keeping the higher-severity instance.

### **3.6 Finding Fingerprinting**

Finding fingerprinting is the foundation of the entire incremental review system. Incremental review logic, comment deduplication, and comment threading all depend on stable fingerprints. This must be built and tested before any other feature that touches Postgres.

**The critical design constraint:** Line numbers are not stable across commits. If a developer pushes a second commit that adds lines above an existing issue, the line numbers shift. A fingerprint that includes line numbers would no longer match the same underlying issue, and the system would re-post a comment the developer has already seen. The fingerprint must be stable across line movement.

**Fingerprint inputs:**

* File path  
* Category  
* Normalized title (lowercase, punctuation stripped, whitespace collapsed)  
* Hash of the code snippet being flagged (or normalized description if no snippet available)

**Line numbers are explicitly excluded from the fingerprint.**

**Implementation:**

import hashlib  
import re

def normalize\_title(title: str) \-\> str:  
    title \= title.lower()  
    title \= re.sub(r'\[^\\w\\s\]', '', title)  
    title \= re.sub(r'\\s+', ' ', title).strip()  
    return title

def hash\_snippet(code\_fix\_or\_description: str) \-\> str:  
    normalized \= re.sub(r'\\s+', ' ', code\_fix\_or\_description).strip()  
    return hashlib.sha256(normalized.encode()).hexdigest()\[:16\]

def generate\_fingerprint(finding: dict) \-\> str:  
    components \= \[  
        finding\["file\_path"\],  
        finding\["category"\],  
        normalize\_title(finding\["title"\]),  
        hash\_snippet(finding.get("code\_fix") or finding\["description"\])  
    \]  
    raw \= "|".join(components)  
    return hashlib.sha256(raw.encode()).hexdigest()

Every finding record in Postgres stores its fingerprint. This single field is what makes the entire incremental review system function.

**Testing requirement:** The fingerprint function must have unit tests covering at minimum: same issue where the file was shifted 10 lines by an unrelated commit (fingerprints must match), and two genuinely different issues on the same line (fingerprints must differ). These tests must pass before the incremental review logic is built on top.

### **3.7 Incremental Review Logic**

On each review run, before posting any comments, the system fetches all finding fingerprints from the previous review of the same PR from Postgres. It compares new findings against stored fingerprints to classify each finding into one of three states:

* **New finding**  fingerprint does not exist in any previous review of this PR → post a fresh top-level inline comment, store the returned `github_comment_id`  
* **Persisted finding**  fingerprint matches a finding from the previous review → reply to the existing comment thread using the stored `github_comment_id` with status language: *"⚠️ Still present after latest changes"*  
* **Resolved finding**  fingerprint existed in the previous review but is absent from the current review → call the GitHub API to mark the original comment as outdated, update status to `resolved` in Postgres

**First review on a PR:** When no prior review exists in Postgres for a given PR number, all findings are treated as new. This branch is tested independently from the update path.

This logic is what separates a tool developers use from a tool developers mute. Without it, every PR update re-posts comments on already-fixed issues. With it, the review feels like a conversation with a reviewer who is paying attention.

### **3.8 Comment Threading and Lifecycle**

All comment state is tracked in Postgres. When a finding's comment is first posted to GitHub, the `github_comment_id` returned by the API is stored on the finding record. All subsequent interactions with that comment  replies, resolution  use this stored ID.

**Comment behavior by finding state:**

* New finding → `POST` a new top-level inline comment, store returned `github_comment_id`  
* Persisted finding → `POST` a reply to the existing thread using `in_reply_to: github_comment_id`  
* Resolved finding → mark original comment as outdated using stored `github_comment_id`, update finding status in Postgres to `resolved`

**Status language** makes the review feel like a conversation rather than repeated broadcasts. Persisted findings reply with *"⚠️ Still present after latest changes"*. Resolved findings display *"✅ Resolved in latest commit"* before being marked outdated.

The 25 inline comment cap applies to new and persisted findings combined. Resolved findings do not count against the cap since they are being closed rather than opened.

### **3.9 Supervisor Agent**

The supervisor receives the combined JSON output from all four specialist agents plus the PR context object (title and description) and performs five operations in sequence:

**1\. Cross-agent deduplication:** Findings are merged when they share the same file, overlapping line ranges, and semantically similar descriptions (initial implementation uses keyword overlap as a heuristic). When merging, the highest severity is kept, categories are combined as a list (e.g. `["bug", "security"]`), descriptions and suggestions are combined, and both agent names are credited. When in doubt, findings are kept separate. Losing a security finding by accidentally merging it with a bug finding is worse than a duplicate comment.

**2\. Confidence-based filtering:** Findings with confidence below 0.6 and severity 1–3 are downgraded by one severity level. Findings with severity 4–5 and low confidence are not silently downgraded  instead, their wording is softened to reflect uncertainty (e.g. *"This may be a critical issue  verify before merging"*). This preserves the urgency of potentially real high-severity issues while being honest about model certainty. Original confidence scores are stored in Postgres alongside the final posted severity to enable calibration analysis over time.

**3\. PR intent filtering:** Each finding is checked against the PR title and description. Findings that the PR description explicitly explains as intentional are suppressed or downgraded. This filtering happens at the supervisor level only  specialist agents never see the PR context, which keeps their detection unbiased.

**4\. Global severity calibration:** A final pass ensures consistent severity scoring across all four agents, since different agents may have calibrated differently on similar issues.

**5\. Executive summary generation:** A markdown paragraph synthesizing the overall PR quality and making a clear merge recommendation based on the highest severities present.

### **3.10 Diff Position Mapping Engine**

This is a core correctness component, not a formatting utility. It sits between the supervisor output and the comment engine. Every finding passes through it before any GitHub API call is made. Its job is to answer one question per finding: can this finding be posted as an inline comment on GitHub, and if so, at exactly what position?

**The problem this solves:** The GitHub inline comment API does not accept raw line numbers. It requires a `position` value  a 1-based integer offset counted from the first line of the unified diff hunk for that file, counting added lines, deleted lines, and context lines together. This is completely different from the line number in the actual file. Agents produce `line_start` and `line_end` as raw file line numbers. Without translation, the GitHub API either silently drops the comment or places it on the wrong line entirely. There is no error returned. The review appears to succeed internally while nothing shows up on the PR.

**An additional constraint that most implementations miss:** GitHub only allows inline comments on added lines (the green `+` lines in the PR diff view). Comments cannot be placed on deleted lines or unchanged context lines. This means some findings that the LLM produces  even correct, high-severity ones  will not have a valid postable position if they refer to a line that is not an added line in the current diff.

**How the mapper works:**

The mapper parses the unified diff for each file and builds a lookup table that maps new-file line numbers to their corresponding diff position, but only for added lines. The parsing logic works as follows:

* Read each hunk header (`@@ -a,b +c,d @@`) to extract the starting line number in the new file  
* Walk through each line of the hunk, incrementing the diff position counter for every line regardless of type  
* For lines marked as added (`+`), record the mapping from new-file line number to diff position  
* For lines marked as deleted (`-`) or context ( ), increment the position counter but do not record a mapping, since these lines cannot receive inline comments

The result is a per-file dictionary:

{ new\_file\_line\_number: diff\_position }

This lookup is built once per review run from the unified diff fetched in the coordinator stage and stored in the graph state. Agents do not interact with it directly.

**Mapping each finding:**

After the supervisor produces its final findings list, the mapper processes each finding:

1. Look up `line_start` in the file's position table  
2. If a valid position exists → attach `diff_position` to the finding, mark `comment_destination` as `inline`  
3. If no valid position exists (line is deleted, context-only, or outside the diff entirely) → mark `comment_destination` as `summary_fallback`, log the failure with file path and line number, and record `mapping_failed = true` in Postgres

The comment engine then simply reads `comment_destination` and routes accordingly. It never attempts to post an inline comment without a pre-validated `diff_position`. The separation between mapping and posting is intentional  the comment engine should never need to handle mapping failures itself.

**Fallback behavior:**

Findings that fail mapping are not lost. They are included in the PR-level summary comment under a clearly labelled section. The summary comment notes that these findings could not be attached to specific lines, and presents them with their file path and line range as context. Developers still see the finding. It is never silently dropped.

**Failure tracking in Postgres:**

The `findings` table stores `diff_position` (nullable), `comment_destination` (`inline` | `summary_fallback`), and `mapping_failed` (boolean). This allows production monitoring of how frequently the fallback fires, which file types or diff patterns trigger it most often, and whether mapping failure rates correlate with specific agents or PR sizes.

### **3.11 GitHub Comment Formatter**

Raw supervisor output, after diff position mapping, is structured JSON with a validated `diff_position` or a `summary_fallback` flag on each finding. The formatter transforms this into GitHub-compatible comment payloads. This separation ensures the supervisor focuses purely on analysis logic, the mapper handles all position validation, and the formatter handles all presentation.

The formatter produces two types of output:

**Inline comments**  attached to specific lines in the diff. These use the pre-validated `diff_position` value attached by the mapper. The formatter never performs its own position calculation. It trusts the mapper entirely.

**Summary comment**  a markdown-formatted overview posted at the PR level containing: a severity breakdown table, top findings across all categories, all findings that were routed to summary fallback due to failed diff position mapping (clearly labelled), findings that exceeded the 25-comment inline cap, and a clear merge recommendation.

Formatting rules:

* Severity 4–5 findings are prefixed with a warning indicator and flagged as blockers  
* Softened-confidence findings include explicit uncertainty language in the comment body  
* Each finding includes the responsible agent(s), the affected line range, and a plain-English explanation  
* Auto-fixable style issues include a corrected code snippet in a fenced code block  
* No more than 25 inline comments are posted per review (new \+ persisted combined). Remaining lower-severity findings are included in the summary comment

### **3.12 Data Persistence Layer**

All review events and findings are stored in PostgreSQL. This serves three purposes: tracking finding state across PR updates, audit trail, and a training dataset for future model fine-tuning.

**Schema overview:**

`reviews` table  one record per PR review run. Stores repository name, PR number, commit SHA, timestamp, total findings count, overall merge recommendation, and per-stage timing breakdowns (coordinator time, per-agent time, supervisor time, mapping time, comment posting time).

`findings` table  one record per individual finding. Stores agent name(s), file path, line range, severity, original confidence, final posted severity, category (as array for merged findings), title, description, suggestion, code fix, fingerprint, diff\_position, comment\_destination, mapping\_failed, github\_comment\_id, and status (`open` | `resolved` | `persisted`). Foreign key to the reviews table.

`agents` table  stores prompt templates and model configuration per agent, enabling prompt versioning without code changes.

**Required schema additions from v2:**

ALTER TABLE findings ADD COLUMN fingerprint VARCHAR(64);  
ALTER TABLE findings ADD COLUMN github\_comment\_id BIGINT;  
ALTER TABLE findings ADD COLUMN status VARCHAR(20) DEFAULT 'open';  
ALTER TABLE findings ADD COLUMN confidence FLOAT;  
ALTER TABLE findings ADD COLUMN original\_severity INTEGER;  
ALTER TABLE findings ADD COLUMN diff\_position INTEGER;  
ALTER TABLE findings ADD COLUMN comment\_destination VARCHAR(20) DEFAULT 'inline';  
ALTER TABLE findings ADD COLUMN mapping\_failed BOOLEAN DEFAULT FALSE;

SQLModel is used as the ORM layer. Database connections are managed with asyncpg connection pooling to handle concurrent review jobs cleanly.

## **4\. Agent Design In Detail**

### **4.1 Prompt Engineering Strategy**

Each agent uses a structured system prompt that defines its role, its output schema, and explicit examples of findings to flag and findings to ignore. All agents are instructed to respond exclusively in a JSON array of finding objects. This makes downstream aggregation reliable and eliminates any need for regex parsing of free-text responses. Prompt templates live in the `/prompts` directory as versioned `.txt` files, enabling prompt changes without code changes.

### **4.2 Finding Schema**

All agents produce findings conforming to this schema:

{  
  "file\_path": "string  path of the file relative to repo root",  
  "line\_start": "integer  starting line of the issue in the new file",  
  "line\_end": "integer  ending line (equals line\_start for single-line issues)",  
  "severity": "integer (1–5)  1=informational, 3=moderate, 5=must fix before merge",  
  "confidence": "float (0.0–1.0)  model's confidence that this is a real issue",  
  "category": "string  one of: bug, security, performance, style",  
  "title": "string  concise one-line title, max 80 chars",  
  "description": "string  plain-English explanation of the issue",  
  "suggestion": "string  concrete recommendation for how to fix it",  
  "code\_fix": "string or null  corrected code snippet, or null if not applicable"  
}

The `diff_position` field is not part of the agent output schema. Agents produce raw line numbers only. Diff position is computed by the mapping engine after the supervisor stage and attached to findings at that point. Agents are not responsible for, and should not attempt to calculate, GitHub diff positions.

### **4.3 Gemini / OpenAI Fallback Logic**

Every agent call goes to Gemini first with a 30-second timeout. If Gemini returns a valid response it is used directly. If Gemini raises an exception or times out, the wrapper logs the failure and immediately retries the identical prompt with OpenAI GPT-4o with a 30-second timeout. If OpenAI also fails, the agent's findings are set to an empty list, a warning is logged in the graph state error list, and the pipeline continues with remaining agents. No single agent failure blocks the review from completing. This logic is centralized entirely in `llm_client.py`.

### **4.4 Context Window Management**

Large pull requests can exceed LLM context limits. The coordinator handles this with the chunking strategy described in section 3.5. Findings from multiple chunks of the same file are merged after processing. Duplicates (same file, overlapping line range, same category) are resolved by keeping the higher-severity instance.

## **5\. Data Flow and State Management**

### **5.1 LangGraph State Schema**

The state object passed between graph nodes carries all information agents need and accumulate:

* Raw webhook payload  
* Extracted PR metadata (repo, PR number, commit SHA, branch, author)  
* PR title and description (for supervisor use)  
* Parsed diff chunks organized by file, with chunking strategy logged per file  
* Per-file diff position lookup tables (built by coordinator from unified diff, used by mapper after supervisor)  
* Individual findings from each agent as they complete (including confidence scores)  
* Aggregated and filtered findings from the supervisor  
* Mapped findings with diff\_position and comment\_destination attached  
* Fingerprint comparison results (new / persisted / resolved)  
* Formatted comment payloads ready for the GitHub API  
* Per-stage timing data  
* A list of errors encountered during processing

State is immutable between nodes  each node receives the current state and returns a new state dictionary with its additions. If any single agent fails, its failure is logged in the error list and the pipeline continues.

### **5.2 Parallel Execution**

After the coordinator preprocesses the diff and seeds state, the graph fans out to all four specialist agents simultaneously via parallel edges. Each agent runs concurrently, making independent LLM calls, with an individual timeout of 45 seconds. Once all four complete or time out, the graph fans back into the supervisor node. A slow or failing agent never blocks the full review.

## **6\. Project File Structure**

code-review-agent/  
├── main.py                      \# FastAPI app, all HTTP endpoints, /review command handler  
├── workflow.py                  \# LangGraph graph definition, nodes, edges, compiled graph  
├── fingerprint.py               \# Finding fingerprint generation and comparison logic  
├── diff\_mapper.py               \# Unified diff parsing, line-number-to-diff-position  
│                                \#   lookup table construction, per-finding position  
│                                \#   validation, summary fallback routing  
├── agents/  
│   ├── \_\_init\_\_.py              \# Exports all agent classes  
│   ├── coordinator.py           \# Diff parsing, chunking, PR context fetching, state setup  
│   ├── bug\_detector.py          \# Bug detection agent  
│   ├── security\_scanner.py      \# Security vulnerability scanning agent  
│   ├── performance\_reviewer.py  \# Performance issue detection agent  
│   ├── style\_checker.py         \# Code style and convention checking agent  
│   └── supervisor.py            \# Aggregation, deduplication, confidence filtering,  
│                                \#   PR intent filtering, summary generation  
├── llm\_client.py                \# Gemini primary \+ OpenAI fallback wrapper  
├── github\_client.py             \# All GitHub API interactions, outbound comment queue  
│                                \#   with exponential backoff  
├── formatter.py                 \# Transforms mapped findings JSON into GitHub comment  
│                                \#   payloads; never performs position calculation itself  
├── incremental.py               \# Fingerprint comparison, comment lifecycle management  
│                                \#   (new / persisted / resolved routing)  
├── models.py                    \# SQLModel database schema  
├── database.py                  \# Connection management, session factory  
├── config.py                    \# Environment variable loading via Pydantic Settings  
├── prompts/                     \# Prompt template .txt files, one per agent  
├── tests/  
│   ├── test\_fingerprint.py      \# Unit tests for fingerprint stability (run first)  
│   ├── test\_diff\_mapper.py      \# Unit tests for diff position mapping:  
│   │                            \#   simple diffs, multi-hunk files, line shifts,  
│   │                            \#   deletion-only diffs, large diffs, invalid  
│   │                            \#   mapping → fallback triggered  
│   ├── test\_incremental.py      \# Tests for new/persisted/resolved classification  
│   ├── test\_agents.py           \# Agent output validation  
│   ├── test\_chunking.py         \# AST and fallback chunking tests  
│   └── test\_webhook.py          \# End-to-end webhook tests with mock payloads  
├── requirements.txt             \# Pinned Python dependencies  
├── Dockerfile                   \# Container definition for Railway  
└── .env.example                 \# Template of all required environment variables

`fingerprint.py`, `diff_mapper.py`, and `incremental.py` are the three most critical correctness components in the system. They are kept isolated from agent and formatter logic to make independent testing straightforward and to make debugging unexpected comment behavior easier.

## **7\. Technology Stack**

| Category | Technology | Rationale |
| ----- | ----- | ----- |
| API Server | FastAPI | Async-native, clean with webhook workloads, auto-generates OpenAPI docs |
| Agent Orchestration | LangGraph | Explicit graph state, supports parallel fan-out, per-node timeouts, production-grade |
| Primary LLM | Google Gemini (gemini-2.5-pro) | Strong code reasoning, generous context window, cost-effective |
| Fallback LLM | OpenAI GPT-4o | Reliable fallback with strong code understanding |
| GitHub Integration | PyGithub | Clean Python wrapper for GitHub REST API |
| Database | PostgreSQL | Reliable, supports JSONB for storing findings arrays, stores fingerprints and comment IDs |
| ORM | SQLModel | Combines SQLAlchemy and Pydantic, clean schema definitions |
| Local Tunneling | ngrok | Exposes localhost for webhook testing during development |
| Deployment | Railway | Already in production use, supports env vars and auto-deploy from GitHub |
| Containerization | Docker | Reproducible environments across dev and production |
| Testing | pytest \+ httpx | httpx provides async test client for FastAPI endpoints |

## **8\. Environment Variables**

GEMINI\_API\_KEY              \# Google Gemini API key (primary LLM)  
OPENAI\_API\_KEY              \# OpenAI API key (fallback LLM)  
GITHUB\_TOKEN                \# GitHub personal access token (repo \+ pull\_request scopes)  
GITHUB\_WEBHOOK\_SECRET       \# Secret for verifying webhook payload signatures  
DATABASE\_URL                \# PostgreSQL connection string (asyncpg format)  
MAX\_FINDINGS\_PER\_REVIEW     \# Max inline comments per review. Defaults to 25  
AGENT\_TIMEOUT\_SECONDS       \# Per-agent LLM timeout. Defaults to 45  
LOG\_LEVEL                   \# INFO in production, DEBUG in development  
SUPPORTED\_AST\_LANGUAGES     \# Comma-separated list of languages for AST chunking.  
                            \#   Defaults to: python,javascript,typescript  
COMMENT\_BACKOFF\_MAX\_SECONDS \# Max backoff cap for outbound comment rate limiting.  
                            \#   Defaults to 60

## **9\. Implementation Roadmap**

### **Phase A  Core Correctness (Before Any Feature Expansion)**

**Goal:** A system that works correctly across multiple PR updates without spamming developers, failing silently on unsupported file types, or dropping findings due to invalid diff positions.

The fingerprint function in `fingerprint.py` is the literal first commit. The diff position mapper in `diff_mapper.py` is the second. Both must have passing unit tests before anything else is built on top of them. Everything else in Phase A is built on these two foundations.

1. Write `fingerprint.py` with full unit tests  first commit, no exceptions  
2. Write `diff_mapper.py` with full unit tests covering simple diffs, multi-hunk files, line shifts, deletion-only diffs, and invalid mapping → summary fallback  second commit, no exceptions  
3. Chunking fallback for unsupported file types (YAML, Terraform, SQL, Go, etc.)  
4. Outbound GitHub comment queue with exponential backoff in `github_client.py`  
5. Incremental review logic in `incremental.py` using fingerprint matching against Postgres  
6. Comment threading and lifecycle  store `github_comment_id`, route to reply or resolve, add status language  
7. First-review branch  explicit handling and testing for the no-prior-review case

### **Phase B  Intelligence Improvements**

**Goal:** Reduce false positives and improve finding quality without changing the core pipeline structure.

1. PR title and description fed into coordinator state, passed to supervisor only (not specialist agents)  
2. Confidence scores on findings  extend schema, update all agent prompts, implement supervisor filtering logic with nuanced high-severity handling  
3. Improved cross-category deduplication with semantic similarity guard  
4. Golden test set of PRs with known issues  run after every prompt change to catch regressions

### **Phase C  Production Polish**

**Goal:** Operational visibility, reliability improvements, and stretch features once the core system is proven on real traffic.

1. `/review` PR comment command for manual re-review triggering and webhook recovery  
2. Per-stage timing stored in Postgres, p95 latency tracking alongside average in success metrics  
3. `GET /reviews/{pr_number}` response includes whether the latest commit SHA has been reviewed  
4. PR status checks  block merge on severity-5 findings via GitHub Commit Status API  
5. Language-aware prompt routing  detect file language and adjust agent prompts accordingly  
6. Human feedback loop via reply commands  defer until one month of real usage data exists  
7. Review analytics dashboard, a simple web UI showing code quality trends from stored findings  
8. Fine-tuning dataset export  format stored findings for supervised fine-tuning

## **10\. Known Limitations and Mitigations**

**LLMs produce false positives.** Prompt engineering with explicit examples of what not to flag reduces this. Confidence scores give the supervisor a tunable mechanism to downgrade low-certainty findings. PR intent filtering at the supervisor level catches the subset of false positives that are explained by the PR description. Human review remains the final gate.

**Large PRs are expensive.** A diff size check caps token usage. For PRs over a configurable line threshold, only changed files are reviewed rather than the full context. The per-agent 6,000 token budget with chunking handles most cases before this cap is reached.

**Gemini and OpenAI both have rate limits.** The per-agent fallback design handles Gemini failures gracefully. Exponential backoff with jitter is applied in `llm_client.py` for sustained high volume.

**GitHub API rate limits at 5,000 requests per hour for reads, with separate secondary limits on writes.** Diff fetches are cached by commit SHA. All comment posting goes through the outbound queue with backoff. Every posting failure is logged explicitly so silent drops do not go undetected.

**AST-based chunking fails on unsupported file types.** The line-count fallback ensures the system never crashes or silently skips files. The chunking strategy used per file is logged and stored so the fallback rate can be monitored in production and the supported language list expanded based on real traffic data.

**Line numbers shift across commits, which would break naive fingerprinting.** The fingerprint design explicitly excludes line numbers, using file path, category, normalized title, and a hash of the code snippet or description instead. This ensures fingerprint stability across line movement.

**GitHub inline comments require diff positions, not raw line numbers, and can only be placed on added lines.** The diff position mapper handles this translation explicitly. Findings that cannot be placed inline  because they refer to deleted lines, context lines, or lines outside the diff  are routed to the summary comment rather than being silently dropped. Mapping failures are logged and tracked in Postgres.

**Webhook delivery failures during server downtime.** The `/review` comment command allows developers to manually trigger a fresh review at any time, covering the majority of missed-event scenarios without requiring complex infrastructure.

**Prompt quality directly determines review quality.** A golden test set of PRs with known issues is built during Phase B and runs after every prompt change to catch regressions before they reach production.

## **11\. Success Metrics**

* End-to-end review time under 90 seconds (average) and under 4 minutes (p95) for PRs under 500 lines changed  
* False positive rate below 15% based on developer feedback over the first month of live use  
* Zero re-posts of already-fixed findings after incremental review is live (monitored via Postgres finding status transitions)  
* Zero silent comment drops  every finding either appears inline, appears in the summary, or has an explicit logged failure entry in Postgres  
* The system handles 19 out of 20 consecutive PR events without crashing across the full pipeline  
* At least one real bug or security issue missed in human review is caught by the agent within the first month on a live repository  
* Core pipeline module test coverage above 70%, with `fingerprint.py`, `diff_mapper.py`, and `incremental.py` at 90%+  
* Comment posting silent failure rate below 0.5% (monitored via explicit failure logging in the outbound queue)  
* Diff position mapping fallback rate below 10% across all findings (monitored via `mapping_failed` field in Postgres)  a high rate indicates agents are flagging too many non-added lines and prompts should be adjusted

*End of Architecture Document  Abdulkareem Sikirulahi, April 2026*

