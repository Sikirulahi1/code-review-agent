import os
from pathlib import Path

# All files to create (relative to code-review-agent/)
files = [
    # Root files
    ".env",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "requirements.txt",
    "README.md",
    "main.py",

    # config/
    "config/__init__.py",
    "config/settings.py",

    # api/
    "api/__init__.py",
    "api/routes/__init__.py",
    "api/routes/webhook.py",
    "api/routes/reviews.py",
    "api/routes/health.py",
    "api/middleware/__init__.py",
    "api/middleware/signature.py",

    # agents/
    "agents/__init__.py",
    "agents/coordinator.py",
    "agents/bug_agent.py",
    "agents/security_agent.py",
    "agents/performance_agent.py",
    "agents/style_agent.py",
    "agents/supervisor.py",

    # services/
    "services/__init__.py",
    "services/github_client.py",
    "services/llm_client.py",
    "services/workflow.py",
    "services/review_service.py",

    # core/
    "core/__init__.py",
    "core/fingerprint.py",
    "core/diff_mapper.py",
    "core/incremental.py",
    "core/formatter.py",

    # db/
    "db/__init__.py",
    "db/database.py",
    "db/models.py",

    # prompts/
    "prompts/coordinator.txt",
    "prompts/bug_agent.txt",
    "prompts/security_agent.txt",
    "prompts/performance_agent.txt",
    "prompts/style_agent.txt",
    "prompts/supervisor.txt",

    # tests/
    "tests/__init__.py",
    "tests/core/test_fingerprint.py",
    "tests/core/test_diff_mapper.py",
    "tests/core/test_incremental.py",
    "tests/core/test_formatter.py",
    "tests/services/test_github_client.py",
    "tests/services/test_llm_client.py",
    "tests/services/test_workflow.py",
    "tests/services/test_review_service.py",
    "tests/agents/test_coordinator.py",
    "tests/agents/test_specialist_agents.py",
    "tests/agents/test_supervisor.py",
    "tests/api/test_webhook.py",
    "tests/api/test_reviews.py",
]

base = Path(".")

for file_path in files:
    full_path = base / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.touch()
    print(f"Created: {file_path}")

print("\nDone! All folders and files created.")