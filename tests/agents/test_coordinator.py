from agents.coordinator import CoordinatorAgent, chunk_patch_by_lines


class _FakeGitHubClient:
	def get_pr_metadata(self, _repo_full_name: str, _pr_number: int) -> dict[str, str]:
		return {
			"title": "Add webhook handler",
			"description": "Implements webhook endpoint",
			"author": "dev",
			"head_sha": "head-1",
			"base_sha": "base-1",
		}

	def fetch_pr_patches(self, _repo_full_name: str, _pr_number: int) -> dict[str, str]:
		large_patch = "\n".join(["@@ -1,1 +1,801 @@"] + [f"+line_{i}" for i in range(1, 802)])
		small_patch = "\n".join([
			"@@ -1,2 +1,3 @@",
			" old",
			"+new_a",
			"+new_b",
		])
		return {
			"api/routes/webhook.py": large_patch,
			"services/workflow.py": small_patch,
		}


def test_chunk_patch_by_lines_splits_large_patch() -> None:
	patch = "\n".join(f"+line_{i}" for i in range(1, 901))

	chunks = chunk_patch_by_lines(patch, chunk_line_limit=400)

	assert len(chunks) == 3


def test_prepare_state_builds_chunks_context_and_position_tables() -> None:
	agent = CoordinatorAgent(github_client=_FakeGitHubClient())

	state = agent.prepare_state("owner/repo", 1)

	assert state["pr_metadata"]["title"] == "Add webhook handler"
	assert state["_pr_context"]["description"] == "Implements webhook endpoint"

	assert "api/routes/webhook.py" in state["diff_chunks"]
	assert len(state["diff_chunks"]["api/routes/webhook.py"]) > 1

	assert "services/workflow.py" in state["position_tables"]
	assert state["position_tables"]["services/workflow.py"]
	assert state["chunking_strategy"]["services/workflow.py"] == "line_count"
	assert state["errors"] == []
