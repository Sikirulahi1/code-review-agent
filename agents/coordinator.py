from __future__ import annotations

from typing import Any

from core.diff_mapper import build_line_to_position_map
from services.github_client import GitHubClient

DEFAULT_CHUNK_LINE_LIMIT = 400


def chunk_patch_by_lines(patch: str, chunk_line_limit: int = DEFAULT_CHUNK_LINE_LIMIT) -> list[str]:
	lines = patch.splitlines()
	if not lines:
		return [""]

	chunks: list[str] = []
	for start in range(0, len(lines), chunk_line_limit):
		chunks.append("\n".join(lines[start:start + chunk_line_limit]))
	return chunks


class CoordinatorAgent:
	def __init__(self, github_client: GitHubClient | None = None) -> None:
		self._github_client = github_client or GitHubClient()

	def prepare_state(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
		metadata = self._github_client.get_pr_metadata(repo_full_name, pr_number)
		patches = self._github_client.fetch_pr_patches(repo_full_name, pr_number)

		diff_chunks: dict[str, list[str]] = {}
		position_tables: dict[str, dict[int, int]] = {}
		chunking_strategy: dict[str, str] = {}

		for file_path, patch in patches.items():
			diff_chunks[file_path] = chunk_patch_by_lines(patch)
			position_tables[file_path] = build_line_to_position_map(patch)
			chunking_strategy[file_path] = "line_count"

		return {
			"pr_metadata": metadata,
			"_pr_context": {
				"title": metadata.get("title", ""),
				"description": metadata.get("description", ""),
			},
			"diff_chunks": diff_chunks,
			"position_tables": position_tables,
			"chunking_strategy": chunking_strategy,
			"errors": [],
		}
