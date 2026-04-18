# **AI Code Review Agent  Full Implementation Guide**

**By Abdulkareem Sikirulahi | Based on Architecture v3.0**

## **Before You Begin: The Mental Model**

Before touching a single file, you need to understand what this system actually *is* at its core. Picture it like a very smart assistant that sits between your developers and GitHub. Every time someone opens a pull request, this assistant wakes up, reads all the code changes, splits the work among four specialized reviewers (one who looks for bugs, one for security problems, one for performance issues, one for code style), waits for all four to finish, then has a senior supervisor look at everything together and decide what's worth posting. Then  and this is the critical part  it figures out exactly where in GitHub's interface each comment should go, checks whether it already said this on a previous version of the same PR, and only then posts the comments.

That's the whole system. Everything in this guide is just the detailed mechanics of making that happen reliably.

## **Part 1: Setting Up Your Environment and Repository**

### **Step 1.1  Create Your Project Folder and Repository**

The very first thing you do is create a new folder on your machine called something like code-review-agent. Inside that folder, you initialize a Git repository. You then create a corresponding repository on GitHub and push your initial empty project there. The reason you want it on GitHub from the very beginning is that Railway (your deployment platform) deploys directly from GitHub, and you'll want that connection set up early so you're not doing it in a rush later.

Your GitHub repository should be private because it will eventually contain references to API keys (even though the keys themselves will live in environment variables, the structure of the project reveals your infrastructure).

### **Step 1.2  Set Up Python and Your Virtual Environment**

This project uses Python. You need Python 3.11 or higher because some of the async features and type hint syntax used in FastAPI and SQLModel work best on newer versions. Once you confirm your Python version, create a virtual environment inside your project folder. The virtual environment keeps this project's dependencies isolated from everything else on your machine. You activate it every single time you work on this project. This is non-negotiable  mixing global packages causes subtle bugs that are extremely hard to diagnose.

### **Step 1.3  Install Your Core Dependencies**

Now you install all the libraries the system depends on. The main ones you'll need are FastAPI (the web server), Uvicorn (the thing that actually runs FastAPI), LangGraph (the agent orchestration framework), LangChain (LangGraph builds on top of this), the Google Generative AI library (for Gemini), the OpenAI library (for the fallback), PyGithub (for talking to GitHub's API), SQLModel (the database ORM), asyncpg (for async PostgreSQL connections), and pytest plus httpx for testing. You'll also need python-dotenv for loading your environment variables from a .env file locally. Install everything at once and immediately pin the versions in a requirements.txt file by running the pip freeze command. This requirements.txt is what Railway and Docker will use to recreate your environment.

### **Step 1.4  Create Your Project File Structure**

Based on the architecture document, you now create all the files and folders your project needs, but you leave them empty for now. The purpose of doing this upfront is so that when you start writing one module, you can already see where everything else lives and how it connects. Create main.py, workflow.py, fingerprint.py, diff\_mapper.py, llm\_client.py, github\_client.py, formatter.py, incremental.py, models.py, database.py, config.py, a folder called agents/ with an \_\_init\_\_.py and individual files for each agent, a prompts/ folder, and a tests/ folder with individual test files. Also create .env.example and Dockerfile as empty files. You'll fill them all in over time.

### **Step 1.5  Set Up Your .env File**

Copy your .env.example and create a real .env file (which you will immediately add to .gitignore so it never gets pushed to GitHub). In this file you put all eight environment variables the system needs: your Gemini API key, your OpenAI API key, your GitHub token, your GitHub webhook secret, your database URL, and the configuration defaults for max findings, agent timeout, log level, supported AST languages, and comment backoff. For now, most of these will have placeholder values. You'll fill them in as you create each external account. The important thing is that config.py reads all configuration exclusively from environment variables using Pydantic Settings  never hardcoded anywhere in the actual code.

## **Part 2: External Accounts and Services Setup**

### **Step 2.1  PostgreSQL Database**

You need a PostgreSQL database. The easiest route for a project like this is to create one on Railway itself (since that's where you're deploying) or use a managed service like Supabase or Neon. Create the database, get the connection string in asyncpg format (which looks like postgresql+asyncpg://user:password@host:port/dbname), and put it in your .env file. Don't create any tables manually  your SQLModel code will handle that automatically when the application starts up for the first time. What you want from this step is just a live, accessible database you can connect to.

### **Step 2.2  GitHub Token**

Go to your GitHub account settings and create a Personal Access Token with the repo and pull\_requests scopes. This token is what allows your system to read PR diffs and post comments. Put it in your .env file. Note that this token acts as *you* on GitHub, so every comment your system posts will appear to come from your account. If this is for a team or production use, you'd eventually set up a GitHub App instead, which gets its own bot identity, but a personal access token is perfectly fine for building and testing.

### **Step 2.3  Webhook Secret**

When you set up the GitHub webhook later, GitHub will ask you for a secret string. This secret is used to sign every webhook payload it sends you, so you can verify the payload actually came from GitHub and wasn't spoofed by someone who found your server URL. Generate a strong random string (at least 32 characters, mix of letters and numbers), put it in your .env file as GITHUB\_WEBHOOK\_SECRET, and keep it safe. You'll enter this same string into GitHub when you configure the webhook.

### **Step 2.4  Gemini API Key**

Go to Google AI Studio (aistudio.google.com), create an API key for the Gemini API, and put it in your .env file. Make sure your project has the Gemini 2.5 Pro model enabled, as that's what the architecture specifies. There are rate limits and potentially costs depending on your usage tier, so familiarize yourself with the free tier limits before you start sending real PR diffs to it.

### **Step 2.5  OpenAI API Key**

Create an OpenAI platform account if you don't have one, add a payment method, generate an API key, and put it in your .env file. This key is only ever used as a fallback when Gemini fails, so you won't use it much during development, but it needs to be there and valid for the fallback logic to work.

### **Step 2.6  ngrok for Local Development**

During development, your webhook server is running on your local machine at something like localhost:8000. GitHub can't reach that URL from the internet. ngrok solves this by creating a temporary public URL that tunnels through to your local machine. Install ngrok, create a free account, and authenticate it on your machine. You'll start it up whenever you want to test real GitHub webhooks hitting your local server. The URL ngrok gives you changes every time you restart it on the free plan, so you'll need to update the GitHub webhook URL each development session. This is slightly annoying but completely manageable during development. In production on Railway, you'll have a stable URL.

## **Part 3: Phase A  Core Correctness (The Foundation)**

The architecture document is very explicit about this: the fingerprint function and the diff position mapper are built first, with passing tests, before anything else. This is not a suggestion  it's the design constraint that makes the entire system work correctly. Every part of the system that comes after depends on these two working perfectly.

### **Step 3.1  Building config.py First**

Even before fingerprint.py, you write config.py because every other module imports settings from it. This file defines a Settings class using Pydantic BaseSettings that reads all your environment variables. It should expose your API keys, webhook secret, database URL, and all the defaults. Every other module accesses configuration by importing from config.py  never directly from os.environ. This centralizes all configuration logic in one place, which makes it easy to test with different settings by overriding just this one object.

### **Step 3.2  Building fingerprint.py  The Absolute First Commit**

This file has one job: given a finding (a dictionary with information about a code issue), produce a stable, consistent hash string that uniquely identifies that issue regardless of what line number it's on. The reason this must come first is that the entire incremental review system  the feature that prevents re-posting comments on already-fixed issues  is built entirely on top of fingerprints. If fingerprints are unstable or wrong, the whole system either spams developers with duplicate comments or silently misses already-seen issues. Both failure modes would make the tool unusable.

The fingerprint is built from four pieces of information: the file path, the category of finding (bug, security, performance, style), the normalized title (lowercased, punctuation stripped, whitespace collapsed), and a hash of the code snippet or description. Line numbers are intentionally and completely excluded. The logic behind this: if a developer pushes a second commit that just adds two lines of comments at the top of a file, all line numbers shift by two. The underlying bug or security issue is still exactly the same. The fingerprint must recognize it as the same issue. That's only possible if line numbers aren't part of the fingerprint.

After writing this file, you immediately write tests/test\_fingerprint.py. The two most critical test cases, as the architecture specifies, are: one test where you take a finding, shift all its line numbers by ten, and verify the fingerprint comes out identical; and one test where you take two genuinely different findings that happen to be on the same line and verify their fingerprints are different. These tests must be green before you move forward. Run them and keep them green forever.

### **Step 3.3  Building diff\_mapper.py  The Second Commit**

This is the second critical correctness component. To understand why it exists, you need to understand how GitHub's inline comment API works. When you want to post a comment on a specific line in a pull request, you can't just say "line 47 of auth.py". GitHub requires a position value, which is a number representing how far into the unified diff that line is. It counts every line in the diff  added lines, deleted lines, context lines  and the position of your target line is its index in that sequence. Additionally, and this is the part that trips most people up, you can only post inline comments on *added* lines (the green \+ lines). You cannot attach a comment to a line that was deleted or a context line that didn't change.

Your agents will produce raw file line numbers because that's what makes sense when looking at code. The diff mapper's job is to translate those raw line numbers into the position values GitHub actually needs, and to figure out which findings can be posted inline at all (because they refer to added lines) versus which ones need to fall back to the PR-level summary comment (because they refer to deleted or context lines).

The mapper works by parsing the unified diff text. It reads each hunk header  those lines that look like @@ \-23,6 \+23,8 @@  to understand which line numbers in the new file this section of the diff covers. Then it walks through every line in the hunk, counting up a position number for every single line regardless of type, but only recording the mapping from new-file-line-number to position for lines that are additions (lines starting with \+). The result is a dictionary for each file that you can look up: "what's the diff position for line 47 of auth.py?" If there's an entry, the line is an addition and you can post a comment there. If there's no entry, the line is either a deletion, an unchanged context line, or completely outside the diff, and the finding must go into the summary comment instead.

After building this, you write tests/test\_diff\_mapper.py. This test file needs to cover: a simple single-hunk diff, a file with multiple hunks, a case where lines shifted because of changes earlier in the file (proving the position math is correct), a diff with only deletions and no additions (verifying you get no valid positions back, since there's nothing to comment on), a large diff, and a case where a finding's line number has no valid position (verifying it gets correctly flagged for summary fallback). These tests must be green before you continue.

### **Step 3.4  Building models.py  Your Database Schema**

Now you define all your database tables using SQLModel. The two main tables are reviews and findings. The reviews table has one row per review run  it stores which repository, which PR number, which commit SHA, when the review happened, how many findings there were, what the overall recommendation was, and timing breakdowns for each stage of the pipeline. The findings table has one row per individual finding, with a foreign key back to the review it came from. It stores everything about the finding: agent name, file path, line numbers, severity, confidence, the fingerprint, the diff position, whether it's going inline or to the summary, whether mapping failed, the GitHub comment ID (once the comment is posted), and the status (open, persisted, or resolved).

The schema also includes the agents table for storing prompt templates with version tracking, but this is lower priority  focus on getting reviews and findings right.

The critical column additions that the architecture calls out are: fingerprint, github\_comment\_id, status, confidence, original\_severity, diff\_position, comment\_destination, and mapping\_failed. Make sure all of these are on the findings table.

### **Step 3.5  Building database.py**

This file handles the actual database connection. It creates the asyncpg connection pool using your DATABASE\_URL from config, provides a function to get a database session, and contains the startup logic that creates all your tables if they don't exist yet. The table creation on startup is what means you never have to manually run SQL against your database  just deploy the application and it sets itself up.

### **Step 3.6  Building the GitHub Client (github\_client.py)**

This is your interface to everything GitHub-related. It wraps PyGithub and handles all the outbound API calls. The key operations are: fetching PR metadata (title, description, author), fetching the PR diff, posting new inline review comments, replying to existing comment threads, resolving outdated comments, creating the PR-level summary review, and optionally setting commit status checks.

The most important thing to get right here is the outbound rate limit handling. GitHub has secondary rate limits on write operations that are separate from the primary 5,000-requests-per-hour limit. These secondary limits are specifically about how frequently you're doing write operations (like posting comments), and violating them causes failures that don't always return a clear error  they can look like silent successes that just don't actually post the comment. To prevent this, all your comment-posting calls need to go through an in-memory queue with exponential backoff. The backoff starts at 1 second and caps at 60 seconds (configurable via COMMENT\_BACKOFF\_MAX\_SECONDS). Every failure must be logged explicitly  you should never have a situation where a comment was supposed to be posted and wasn't, and you don't know about it.

Also cache diff fetches by commit SHA. If the same commit triggers multiple webhook deliveries (which can happen), you don't want to fetch the same diff multiple times.

### **Step 3.7  Building the LLM Client (llm\_client.py)**

This file centralizes all your AI API calls and implements the Gemini/OpenAI fallback logic. The way it works is: any agent that wants to make an LLM call goes through a single wrapper function here. That function sends the request to Gemini with a 30-second timeout. If Gemini returns a valid response, great  use it. If Gemini raises any exception or times out, the wrapper logs that failure and immediately retries the exact same prompt with OpenAI GPT-4o, also with a 30-second timeout. If OpenAI also fails, the wrapper returns an empty list of findings, logs a warning, and lets the pipeline continue.

The critical design principle here: no single agent failure should ever block the rest of the review from completing. If the security scanner has a bad day, the bug detector, performance reviewer, and style checker should still produce their findings.

Also apply exponential backoff with jitter in this file for sustained high-volume scenarios where you're hitting rate limits across many concurrent reviews.

### **Step 3.8  Building the Agents**

Now you build the five agents. Start with the coordinator, then the four specialists, and save the supervisor for last because it depends on understanding what the others produce.

**The Coordinator Agent** is the setup agent. It doesn't make LLM calls in the same way the others do  its job is to prepare everything. It takes the raw webhook payload and PR metadata, calls the GitHub API to get the full unified diff, parses that diff into chunks organized by file, applies the chunking strategy (AST-based for Python/JavaScript/TypeScript, line-count-based for everything else), calls the diff mapper to build the position lookup tables for every file, and stores all of this in the LangGraph state so every subsequent agent has what it needs. It also fetches the PR title and description, but stores them in a part of the state that's only accessible to the supervisor  specialist agents never see them.

**The Chunking Logic**: For each file in the diff, check if it's a supported language for AST chunking. If the file is Python, JavaScript, or TypeScript and its diff exceeds 6,000 tokens, use a lightweight AST parser to split the diff at function or class boundaries. If the file is any other format  YAML, Terraform, SQL, Go, Rust, whatever  fall back to simple line-count-based splitting at 400 lines per chunk. The fallback doesn't produce semantically perfect chunks but it doesn't crash and it doesn't skip files. Log which strategy was used for each file in the graph state so you can monitor the fallback rate in production.

**The Bug Detector Agent** takes the parsed diff chunks and looks for logic errors: null pointer risks, unhandled exceptions, off-by-one errors, incorrect conditional logic, data type mismatches. It calls the LLM through llm\_client.py and receives back a JSON array of findings following the finding schema. Each finding has a file path, line range, severity 1-5, confidence 0-1, category set to "bug", a short title, a plain-English description, a concrete suggestion for fixing it, and optionally a corrected code snippet.

**The Security Scanner Agent** does the same thing but focuses on security: hardcoded secrets, SQL injection vulnerabilities, command injection risks, authentication flaws, unsafe input handling, insecure dependencies, exposed sensitive data in logs. It should also reference CWE identifiers where applicable (CWE is the Common Weakness Enumeration  a standardized catalog of software weaknesses).

**The Performance Reviewer Agent** looks for performance problems: inefficient loops, N+1 query problems (where you're doing one database query per item in a list when you could do one query for all items), memory leaks, blocking I/O calls inside async functions, unnecessary recomputation of values that could be cached.

**The Style Checker Agent** looks at code quality and convention issues: naming conventions, missing docstrings on public functions and classes, dead code (code that's never executed), high cyclomatic complexity (functions that have too many branches and are hard to understand), inconsistent formatting. For style issues, the code fix field should almost always be populated with a corrected version.

**The Supervisor Agent** is the most complex. It receives the combined JSON output from all four specialists plus the PR context and performs five operations in order. First, cross-agent deduplication: if the bug detector flagged the same issue the security scanner also flagged, merge them into one finding. Keep the higher severity, combine the categories into a list, combine the descriptions. When uncertain whether two findings are really the same issue, keep them separate  it's better to have two slightly redundant comments than to accidentally merge a security issue into a bug finding and lose the security classification. Second, confidence-based filtering: findings with confidence below 0.6 and severity 1-3 get downgraded by one severity level. But for severity 4-5 findings with low confidence, don't silently downgrade them  instead, soften the wording to say "This may be a critical issue  verify before merging." You want developers to check potential critical issues even when the model isn't sure. Third, PR intent filtering: check each finding against the PR title and description. If the PR description says "removing the old auth system, will add the new one in the next PR", and you have a finding about missing authentication, suppress it or downgrade it. Fourth, global severity calibration: make sure the severity scale is consistent across all four agents. Fifth, generate an executive summary paragraph in markdown that describes the overall quality of the PR and makes a clear merge recommendation.

### **Step 3.9  Building workflow.py  The LangGraph Graph**

This is where you wire all the agents together into a directed graph. The structure is: coordinator node first, then a parallel fan-out to all four specialist agents simultaneously, then a fan-in to the supervisor node, then the diff mapper runs over the supervisor's output, then the formatter, then the comment engine.

LangGraph works by defining a StateGraph with a state schema (the shared object all nodes can read from and write to), adding nodes (each agent is a node), and adding edges (which define the execution order and any conditional logic). The parallel fan-out is done with parallel edges from the coordinator to all four specialists. The fan-in is done by making all four specialists connect to the supervisor.

Each node receives the current state, does its work, and returns a new state dictionary with only the fields it changed or added. State is immutable  nodes don't modify state in place, they return modifications. This makes debugging much easier because you can inspect exactly what each node received and what it added.

Set a 45-second timeout on each specialist agent. A slow Gemini call should not block the entire review for 45 seconds plus whatever the other agents need  they run in parallel, so the total wait time for the parallel stage is as long as the slowest agent, not the sum of all agents.

### **Step 3.10  Building incremental.py**

This file implements the logic that makes the system feel like a real conversation rather than a spam machine. Before posting any comments on a PR update, this module fetches all the fingerprints from the previous review of the same PR from the database. It then compares the new set of findings against those old fingerprints and classifies each finding into one of three states.

A *new finding* is one whose fingerprint doesn't appear in any previous review of this PR. Post a fresh comment. Store the GitHub comment ID that comes back from the API.

A *persisted finding* is one whose fingerprint matches something from the previous review. Don't post a new top-level comment  instead, reply to the existing comment thread using the stored GitHub comment ID, saying "⚠️ Still present after latest changes."

A *resolved finding* is one that appeared in the previous review but doesn't appear in the current review at all. Call the GitHub API to mark that original comment as outdated, and update its status in the database to "resolved."

The first-review case  when there are no previous reviews in the database for this PR  needs explicit handling. All findings are classified as new. Write a separate test for this case.

Write tests/test\_incremental.py covering: the first review case, the case where some findings persist and some are new, and the case where previous findings are resolved.

### **Step 3.11  Building formatter.py**

The formatter takes the supervisor's findings (already with diff positions attached by the mapper) and transforms them into the actual payloads you'll send to the GitHub API. It produces two types of output: inline comment payloads for findings with valid diff positions, and a summary comment payload for everything else.

For inline comments: take the pre-validated diff\_position from the finding (never recalculate it yourself  trust the mapper completely), format the finding into a readable markdown comment with severity level, description, suggestion, and optionally a fenced code block with the fix.

For the summary comment: produce a well-structured markdown document with a severity breakdown table at the top, then the top findings from across all categories, then a clearly labelled section for findings that couldn't be placed inline (due to mapping failures), then findings that got bumped due to the 25-comment limit, and finally the merge recommendation from the supervisor's executive summary.

Formatting rules to remember: severity 4-5 findings get a warning emoji prefix and are marked as blockers. Findings where the supervisor softened the wording due to low confidence should include explicit uncertainty language. Each finding shows which agent(s) found it. No more than 25 inline comments per review (new plus persisted combined).

### **Step 3.12  Building main.py  The FastAPI Server**

This is your application entry point. It creates the FastAPI app, registers the startup and shutdown events (which initialize and clean up the database connection pool), and defines the endpoints.

The /webhook endpoint is the most important one. It receives POST requests from GitHub, verifies the HMAC-SHA256 signature using your webhook secret, determines what kind of event it received (a pull request event or an issue comment event), and dispatches the review job as a background task so it can immediately return a 200 response to GitHub without making GitHub wait for the full review to complete.

Signature verification: GitHub sends a header called X-Hub-Signature-256 that contains an HMAC-SHA256 hash of the request body signed with your webhook secret. You compute the same hash yourself and compare. If they don't match, return 403 immediately  someone is sending fake webhook requests to your server. Never skip this check.

The /review command: when someone posts a comment on a PR that contains the text /review, GitHub sends an issue\_comment event to your webhook. When you see this, trigger a fresh full review of that PR regardless of what commit it's currently on. This is both a manual re-review trigger and a recovery mechanism for webhook deliveries you might have missed during server downtime.

The /health endpoint just returns a 200 with a simple status message. Railway uses this to know your service is running.

The /reviews/{pr\_number} endpoint returns the stored review data for a given PR number, including whether the latest commit SHA has already been reviewed. This is useful for monitoring and for developers who want to see the review history.

## **Part 4: Testing Your System Locally**

### **Step 4.1  Unit Tests First**

Run your unit tests before you do any integration testing. At a minimum you need: fingerprint tests passing (the same-issue-with-shifted-lines test and the different-issues-same-line test), diff mapper tests passing (all the cases listed in step 3.3), and incremental review tests passing. These three test files are the ones the architecture specifically calls out as needing 90%+ coverage. Run them constantly as you build  they should never break.

### **Step 4.2  Starting the Local Server**

Once you have the core files built, start the FastAPI server locally using Uvicorn. You should see it start up at localhost:8000. Check the /health endpoint in your browser  if it returns a status message, the server is running and connected to the database. If you see database connection errors, your DATABASE\_URL is either wrong or the database isn't reachable.

### **Step 4.3  Setting Up ngrok**

Start ngrok pointed at port 8000\. It will give you a public URL like https://abc123.ngrok.io. This URL is temporarily your server's public address. Go to your GitHub repository settings, find Webhooks, and add a new webhook. Set the payload URL to your ngrok URL plus /webhook (e.g., https://abc123.ngrok.io/webhook). Set content type to application/json. Enter your webhook secret. Under "Which events would you like to trigger this webhook?", select "Pull requests" and "Issue comments." Save it. GitHub will immediately send a ping event to verify the connection  you should see it arrive in your server logs.

### **Step 4.4  Your First Real Webhook Test**

Open a pull request in your repository with some obviously problematic code  maybe a function with a hardcoded password string, a bare except clause that swallows all errors, or an obvious N+1 query pattern. Watch your server logs as the webhook arrives, the review runs, and comments appear on the PR. The first time this works end-to-end is a significant milestone.

Things that will probably go wrong the first time: the diff position mapper will have edge cases you didn't test, the LLM will return findings with line numbers that are outside the diff, the rate limiting on comment posting will trigger sooner than you expect. These are all normal  each one teaches you something about the real-world behavior that's hard to simulate in unit tests.

### **Step 4.5  Testing the Incremental Review**

After your first end-to-end test works, push a second commit to the same PR. Some of the issues from the first review should now show "⚠️ Still present after latest changes" as replies to the original comments. If you fixed any of the issues, those original comments should be marked as outdated. Verify this behavior is correct by looking at both the GitHub PR comments and the database records.

## **Part 5: Deploying to Railway**

### **Step 5.1  Building the Dockerfile**

Your Dockerfile needs to: start from a Python base image, copy your requirements.txt and install all dependencies, copy the rest of your application code, expose port 8000, and set the command to run Uvicorn. Railway reads this Dockerfile to build and run your service. Keep it simple and straightforward  this is not a multi-stage build and doesn't need to be.

### **Step 5.2  Creating the Railway Project**

Go to Railway, create a new project, and connect it to your GitHub repository. Every time you push to your main branch, Railway will automatically rebuild and redeploy your service. Also add a PostgreSQL service inside the same Railway project  Railway makes it easy to spin one up and will automatically give you the DATABASE\_URL as an environment variable.

### **Step 5.3  Setting Environment Variables on Railway**

In your Railway service settings, add all the environment variables from your .env file. Railway's PostgreSQL service will set DATABASE\_URL automatically. You add the API keys, webhook secret, and configuration defaults manually. Double-check all of them because a missing environment variable will cause a silent failure that can be very confusing to debug.

### **Step 5.4  Updating the GitHub Webhook**

Once Railway deploys your service, you get a stable public URL (something like https://your-app.railway.app). Go back to your GitHub repository webhook settings and update the URL from the ngrok URL to the Railway URL. You no longer need ngrok for production  it's still useful for local development and debugging.

## **Part 6: Phase B  Intelligence Improvements**

Once Phase A is fully working and you have the system running on real PRs, you move to Phase B. Don't start Phase B until Phase A is proven  the incremental review, fingerprinting, and diff mapping all need to be working reliably first.

### **Step 6.1  PR Context Integration**

The architecture says PR title and description should go only to the supervisor, not to specialist agents. Implement the coordinator fetching the PR title and description and storing them in a protected part of the graph state. Verify that the specialist agents' prompts don't reference this context. Then extend the supervisor's prompt to use the PR title and description for intent filtering. The specific case you're solving: if a PR description says "deliberately removing rate limiting for the performance test environment," you don't want the security scanner's finding about missing rate limiting to become a blocking comment. The supervisor reads the PR description and suppresses or downgrades that finding.

### **Step 6.2  Confidence Score Handling**

Extend the finding schema so agents report confidence scores. Update every agent's system prompt to include instructions on assigning confidence values (0.0 meaning "I'm guessing" to 1.0 meaning "this is definitely a problem"). Then implement the supervisor's confidence-based filtering: downgrade low-confidence low-severity findings, but soften the wording of low-confidence high-severity findings rather than suppressing them. Store both the original confidence and the final posted severity in the database so you can analyze calibration over time.

### **Step 6.3  Improved Deduplication**

The initial deduplication uses keyword overlap as a heuristic. Once you have real PR data from production, you'll be able to see which duplicate findings are getting through. Improve the deduplication logic based on what you observe. The architecture warns explicitly: when uncertain, keep findings separate. Losing a security finding by accidentally merging it with a bug finding is worse than a slightly redundant comment.

### **Step 6.4  Golden Test Set**

This is critically important for prompt quality. Collect a set of real PRs  maybe 10-20  where you know exactly what issues exist. Document the expected findings for each one: which files, what severity, what category. Run these PRs through your agent pipeline and verify the output matches expectations. Any time you change a prompt, run this golden test set again before deploying. This catches prompt regressions before they hit production.

---

## **Part 7: Phase C  Production Polish**

### **Step 7.1  Timing and Monitoring**

Add per-stage timing to every step of the pipeline and store the timing data in the reviews table. Track both average and p95 latency. Your targets are under 90 seconds average and under 4 minutes p95 for PRs under 500 changed lines. If you're exceeding these, the timing data tells you exactly which stage is the bottleneck.

### **Step 7.2  PR Status Checks**

Integrate with GitHub's commit status API so that PRs with severity-5 findings get a failing status check that blocks merging until the issues are addressed. This requires the GitHub token to have the statuses scope. Be careful here  severity-5 issues are "must fix before merge" issues, so blocking is the right behavior, but you want to make sure your severity calibration is good before enabling this, otherwise you'll block legitimate PRs.

### **Step 7.3  Language-Aware Prompt Routing**

Instead of sending every diff to the same generic agent prompt, detect what language the files are in and adjust the prompt accordingly. A Python agent prompt can reference Python-specific patterns like improper use of \_\_init\_\_ or missing \_\_all\_\_ exports. A JavaScript prompt can reference async/await pitfalls or prototype chain issues. This makes the findings significantly more relevant.

### **Step 7.4  Analytics Dashboard**

Once you have a few weeks of production data in PostgreSQL, build a simple web UI (or a read-only page on your existing FastAPI app) that shows code quality trends: finding frequency by category over time, which files have the most recurring issues, false positive rate if you're tracking developer feedback. This turns the database you've been building up into actionable insight.

---

## **Part 8: Maintaining and Iterating**

### **Step 8.1  Monitoring Production**

The success metrics in the architecture document are specific and measurable. Track them actively: end-to-end review time (average and p95), false positive rate (requires developer feedback mechanism), zero re-posts of already-fixed findings (query the database for persisted findings that were previously resolved), zero silent comment drops (check the explicit failure logs), mapping fallback rate (query mapping\_failed \= true as a percentage of total findings). If the mapping fallback rate goes above 10%, your agents are flagging too many non-added lines and the prompts need adjustment.

### **Step 8.2  Prompt Iteration**

Prompts are the most frequently changed part of the system because they directly determine review quality. The architecture stores prompts as versioned .txt files in the /prompts directory, which means you can change a prompt without touching any code. Every time you change a prompt, run the golden test set. Track which prompt version was used for each review in the database so you can correlate prompt changes with finding quality changes.

### **Step 8.3  Expanding AST Language Support**

The initial AST chunking supports Python, JavaScript, and TypeScript. As you see from the chunking\_strategy logs which languages are frequently falling back to line-count chunking, add AST support for those languages. Go is probably the next most common in a typical backend codebase.

### **Step 8.4  Human Feedback Loop**

After one month of real usage data, consider adding a reply command system where developers can reply to a finding with /false-positive or /fixed to give explicit feedback. The architecture recommends waiting a full month before building this because you want to understand real usage patterns before designing the feedback interface. Feedback data becomes your fine-tuning dataset for improving the models over time.

## **Summary of the Build Order**

The sequence matters enormously here. Build in this order and don't skip ahead:

Start with config.py because everything imports from it. Then fingerprint.py with its tests. Then diff\_mapper.py with its tests. Then models.py and database.py. Then github\_client.py with rate limiting. Then llm\_client.py with fallback logic. Then the coordinator agent, then the four specialist agents, then the supervisor. Then workflow.py to wire everything together. Then incremental.py with its tests. Then formatter.py. Then main.py. Then deploy to Railway and test with real PRs. Then Phase B. Then Phase C.

The reason for this exact order is that each module depends on the ones before it being correct. If you build the comment formatter before the diff mapper is tested, you'll be building on a potentially shaky foundation and when things go wrong (and they will) you won't know which layer the problem is in.

The most important principle throughout the entire build: write the test before you call a module done. The three files the architecture specifically calls out  fingerprint.py, diff\_mapper.py, and incremental.py  should be at 90%+ test coverage before you build anything that depends on them. Everything else should aim for 70%+. Tests are not an afterthought here  they're the foundation that lets you change things confidently as the system grows.

