code-review-agent/
│
├── .env                                   # Local secrets (never commit this)
├── .env.example                           # Template with all required env var names
├── .gitignore
├── Dockerfile
├── requirements.txt
├── README.md
│
├── main.py                                # FastAPI app entry point, registers routers
│
├── config/
│   ├── __init__.py
│   └── settings.py                        # Pydantic Settings — all env vars loaded here
│
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── webhook.py                     # POST /webhook, POST /webhook/test
│   │   ├── reviews.py                     # GET /reviews/{pr_number}
│   │   └── health.py                      # GET /health
│   └── middleware/
│       ├── __init__.py
│       └── signature.py                   # HMAC-SHA256 webhook signature verification
│
├── agents/
│   ├── __init__.py
│   ├── coordinator.py                     # Parses diff, chunks by file, seeds graph state
│   ├── bug_agent.py                       # Specialist: logic errors, null refs, edge cases
│   ├── security_agent.py                  # Specialist: vulns, injection, secrets, auth
│   ├── performance_agent.py               # Specialist: complexity, N+1 queries, blocking
│   ├── style_agent.py                     # Specialist: naming, structure, doc, complexity
│   └── supervisor.py                      # Aggregates, deduplicates, filters, ranks
│
├── services/
│   ├── __init__.py
│   ├── github_client.py                   # All GitHub API calls + outbound comment queue
│   ├── llm_client.py                      # Gemini primary + OpenAI fallback, retry/backoff
│   ├── workflow.py                        # LangGraph graph definition, wires agents together
│   └── review_service.py                  # Orchestrates a full review job end-to-end
│
├── core/
│   ├── __init__.py
│   ├── fingerprint.py                     # Stable finding fingerprint logic (no line numbers)
│   ├── diff_mapper.py                     # Unified diff → GitHub position mapper
│   ├── incremental.py                     # Compares new findings to prior review
│   └── formatter.py                       # Formats findings into GitHub comment markdown
│
├── db/
│   ├── __init__.py
│   ├── database.py                        # Async engine setup, session factory, table init
│   └── models.py                          # SQLModel table schemas (Review, Finding, etc.)
│
├── prompts/
│   ├── coordinator.txt
│   ├── bug_agent.txt
│   ├── security_agent.txt
│   ├── performance_agent.txt
│   ├── style_agent.txt
│   └── supervisor.txt
│
└── tests/
    ├── __init__.py
    ├── core/
    │   ├── test_fingerprint.py            # Must reach 90%+ coverage
    │   ├── test_diff_mapper.py            # Must reach 90%+ coverage
    │   ├── test_incremental.py            # Must reach 90%+ coverage
    │   └── test_formatter.py
    ├── services/
    │   ├── test_github_client.py
    │   ├── test_llm_client.py
    │   ├── test_workflow.py
    │   └── test_review_service.py
    ├── agents/
    │   ├── test_coordinator.py
    │   ├── test_specialist_agents.py
    │   └── test_supervisor.py
    └── api/
        ├── test_webhook.py                # FastAPI endpoint tests via httpx
        └── test_reviews.py