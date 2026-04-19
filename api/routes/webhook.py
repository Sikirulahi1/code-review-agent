from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from services.review_service import ReviewService, review_service

router = APIRouter(tags=["webhook"])


def get_review_service() -> ReviewService:
	return review_service


def _extract_repo_and_pr(payload: dict[str, Any]) -> tuple[str, int]:
	repo = payload.get("repository") or {}
	pull_request = payload.get("pull_request") or {}
	issue = payload.get("issue") or {}

	repo_full_name = repo.get("full_name")
	pr_number = pull_request.get("number")

	if pr_number is None and isinstance(issue.get("pull_request"), dict):
		pr_number = issue.get("number")

	if not repo_full_name or not isinstance(pr_number, int):
		raise HTTPException(status_code=400, detail="Invalid webhook payload")

	return repo_full_name, pr_number


def _should_trigger_review(event_name: str, payload: dict[str, Any]) -> bool:
	if event_name == "pull_request":
		return str(payload.get("action") or "") in {"opened", "synchronize", "reopened"}

	if event_name == "issue_comment":
		comment = payload.get("comment") or {}
		issue = payload.get("issue") or {}
		body = str(comment.get("body") or "")
		return "/review" in body and isinstance(issue.get("pull_request"), dict)

	return False


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    review_service: ReviewService = Depends(get_review_service),
    x_github_event: str = Header(default="", alias="X-GitHub-Event"),
) -> dict[str, Any]:
    payload = await request.json()
    event_name = x_github_event or "unknown"

    if not _should_trigger_review(event_name, payload):
        return {"status": "ignored", "event": event_name}

    repo_full_name, pr_number = _extract_repo_and_pr(payload)
    background_tasks.add_task(review_service.run_review, repo_full_name, pr_number)

    return {
        "status": "accepted",
        "event": event_name,
        "repo_full_name": repo_full_name,
        "pr_number": pr_number,
    }


@router.post("/webhook/test")
async def test_webhook(
    payload: dict[str, Any],
    review_service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    repo_full_name, pr_number = _extract_repo_and_pr(payload)
    result = await review_service.run_review(repo_full_name, pr_number)
    return {"status": "ok", "result": result}
