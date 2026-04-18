from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from pydantic import SecretStr
from fastapi.testclient import TestClient

from api.routes.webhook import get_review_service
from config import settings
from main import app


class _FakeReviewService:
	def __init__(self) -> None:
		self.calls: list[tuple[str, int]] = []

	async def run_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
		self.calls.append((repo_full_name, pr_number))
		return {
			"repo_full_name": repo_full_name,
			"pr_number": pr_number,
			"findings": [],
		}


def _pr_payload(action: str = "opened") -> dict[str, Any]:
	return {
		"action": action,
		"repository": {"full_name": "owner/repo"},
		"pull_request": {"number": 5},
	}


def _issue_comment_payload(comment_body: str = "/review") -> dict[str, Any]:
	return {
		"repository": {"full_name": "owner/repo"},
		"issue": {
			"number": 7,
			"pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/7"},
		},
		"comment": {"body": comment_body},
	}


def _set_webhook_secret(monkeypatch, secret: str = "test-secret") -> str:
	monkeypatch.setattr(settings, "github_webhook_secret", SecretStr(secret))
	return secret


def _post_signed_webhook(client: TestClient, event: str, payload: dict[str, Any], secret: str):
	body = json.dumps(payload).encode("utf-8")
	signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

	return client.post(
		"/webhook",
		headers={
			"X-GitHub-Event": event,
			"X-Hub-Signature-256": f"sha256={signature}",
			"Content-Type": "application/json",
		},
		content=body,
	)


def test_webhook_ignores_unhandled_event(monkeypatch) -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service
	secret = _set_webhook_secret(monkeypatch)

	with TestClient(app) as client:
		response = _post_signed_webhook(
			client,
			"ping",
			{"zen": "keep it logically awesome"},
			secret,
		)

	assert response.status_code == 200
	assert response.json()["status"] == "ignored"
	assert fake_service.calls == []
	app.dependency_overrides.clear()


def test_webhook_accepts_pull_request_event_and_runs_review(monkeypatch) -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service
	secret = _set_webhook_secret(monkeypatch)

	with TestClient(app) as client:
		response = _post_signed_webhook(client, "pull_request", _pr_payload(), secret)

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "accepted"
	assert body["repo_full_name"] == "owner/repo"
	assert body["pr_number"] == 5
	assert fake_service.calls == [("owner/repo", 5)]
	app.dependency_overrides.clear()


def test_webhook_accepts_issue_comment_review_command(monkeypatch) -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service
	secret = _set_webhook_secret(monkeypatch)

	with TestClient(app) as client:
		response = _post_signed_webhook(client, "issue_comment", _issue_comment_payload(), secret)

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "accepted"
	assert body["pr_number"] == 7
	assert fake_service.calls == [("owner/repo", 7)]
	app.dependency_overrides.clear()


def test_webhook_rejects_invalid_signature(monkeypatch) -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service
	_set_webhook_secret(monkeypatch)

	with TestClient(app) as client:
		response = client.post(
			"/webhook",
			headers={
				"X-GitHub-Event": "pull_request",
				"X-Hub-Signature-256": "sha256=invalid",
			},
			json=_pr_payload(),
		)

	assert response.status_code == 403
	assert response.json()["detail"] == "Invalid webhook signature"
	assert fake_service.calls == []
	app.dependency_overrides.clear()


def test_webhook_test_endpoint_runs_review_immediately() -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service

	with TestClient(app) as client:
		response = client.post("/webhook/test", json=_pr_payload())

	assert response.status_code == 200
	body = response.json()
	assert body["status"] == "ok"
	assert body["result"]["pr_number"] == 5
	assert fake_service.calls == [("owner/repo", 5)]
	app.dependency_overrides.clear()
