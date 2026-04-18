from __future__ import annotations

from typing import Any

import pytest

from services.review_service import ReviewService


class _FakeWorkflowService:
	def __init__(self, state: dict[str, Any]) -> None:
		self._state = state
		self.calls: list[tuple[str, int]] = []

	def run_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
		self.calls.append((repo_full_name, pr_number))
		return self._state


@pytest.mark.anyio
async def test_run_review_builds_result_and_caches_latest_review() -> None:
	workflow = _FakeWorkflowService(
		{
			"pr_metadata": {"title": "Title"},
			"summary": {"raw_count": 2, "deduped_count": 1, "final_count": 1},
			"errors": ["minor issue"],
			"final_findings": [{"title": "Finding A"}],
		}
	)
	service = ReviewService(workflow_service=workflow)
	stored: dict[tuple[str, int], dict[str, Any]] = {}

	async def _persist(result: dict[str, Any]) -> None:
		stored[(str(result["repo_full_name"]), int(result["pr_number"]))] = result

	async def _load(repo_full_name: str, pr_number: int) -> dict[str, Any] | None:
		return stored.get((repo_full_name, pr_number))

	service._persist_result = _persist  # type: ignore[method-assign]
	service._load_latest_review = _load  # type: ignore[method-assign]

	result = await service.run_review("owner/repo", 12)

	assert workflow.calls == [("owner/repo", 12)]
	assert result["repo_full_name"] == "owner/repo"
	assert result["pr_number"] == 12
	assert result["pr_metadata"]["title"] == "Title"
	assert result["summary"]["final_count"] == 1
	assert result["errors"] == ["minor issue"]
	assert result["findings"][0]["title"] == "Finding A"
	assert "reviewed_at" in result

	latest = await service.get_latest_review("owner/repo", 12)
	assert latest == result


@pytest.mark.anyio
async def test_get_latest_review_returns_none_when_missing() -> None:
	service = ReviewService(workflow_service=_FakeWorkflowService({}))

	async def _load(_repo_full_name: str, _pr_number: int) -> dict[str, Any] | None:
		return None

	service._load_latest_review = _load  # type: ignore[method-assign]

	assert await service.get_latest_review("owner/repo", 999) is None
