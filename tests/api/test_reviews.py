from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.routes.webhook import get_review_service
from main import app


class _FakeReviewService:
	def __init__(self, latest: dict[tuple[str, int], dict[str, Any]] | None = None) -> None:
		self._latest = latest or {}

	async def get_latest_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any] | None:
		return self._latest.get((repo_full_name, pr_number))


def test_get_review_returns_latest_review() -> None:
	fake_service = _FakeReviewService(
		{
			("owner/repo", 4): {
				"repo_full_name": "owner/repo",
				"pr_number": 4,
				"findings": [{"title": "F1"}],
			}
		}
	)
	app.dependency_overrides[get_review_service] = lambda: fake_service

	with TestClient(app) as client:
		response = client.get("/reviews/4", params={"repo_full_name": "owner/repo"})

	assert response.status_code == 200
	body = response.json()
	assert body["repo_full_name"] == "owner/repo"
	assert body["pr_number"] == 4
	assert body["findings"][0]["title"] == "F1"
	app.dependency_overrides.clear()


def test_get_review_returns_404_when_missing() -> None:
	fake_service = _FakeReviewService()
	app.dependency_overrides[get_review_service] = lambda: fake_service

	with TestClient(app) as client:
		response = client.get("/reviews/999", params={"repo_full_name": "owner/repo"})

	assert response.status_code == 404
	assert response.json()["detail"] == "Review not found"
	app.dependency_overrides.clear()
