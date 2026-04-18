from __future__ import annotations

from types import SimpleNamespace

from services.github_client import GitHubClient


class _FakePR:
	def __init__(self, files: list[SimpleNamespace], sha: str = "abc123") -> None:
		self.head = SimpleNamespace(sha=sha)
		self.base = SimpleNamespace(sha="base123")
		self.title = "Title"
		self.body = "Body"
		self.user = SimpleNamespace(login="user")
		self._files = files
		self.review_comment_calls = 0

	def get_files(self):
		return self._files

	def create_review_comment(self, **kwargs):
		self.review_comment_calls += 1
		return kwargs

	def create_review(self, **kwargs):
		return kwargs


class _FakeRepo:
	def __init__(self, pr: _FakePR) -> None:
		self._pr = pr

	def get_pull(self, _pr_number: int) -> _FakePR:
		return self._pr


class _FakeGithub:
	def __init__(self, repo: _FakeRepo) -> None:
		self._repo = repo
		self.repo_calls = 0

	def get_repo(self, _repo_name: str) -> _FakeRepo:
		self.repo_calls += 1
		return self._repo


def test_fetch_pr_patches_uses_cache_per_commit_sha() -> None:
	files = [
		SimpleNamespace(filename="a.py", patch="@@ -1 +1 @@\n+print('a')"),
		SimpleNamespace(filename="b.py", patch="@@ -1 +1 @@\n+print('b')"),
	]
	fake_pr = _FakePR(files=files, sha="sha-1")
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	first = client.fetch_pr_patches("owner/repo", 1)
	second = client.fetch_pr_patches("owner/repo", 1)

	assert first == second
	assert first["a.py"]
	assert first["b.py"]


def test_queue_and_flush_posts_inline_comments() -> None:
	fake_pr = _FakePR(files=[])
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	client.queue_inline_comment(
		repo_full_name="owner/repo",
		pr_number=1,
		body="Test",
		commit_id="sha",
		path="a.py",
		position=3,
	)
	client.flush_comment_queue()

	assert fake_pr.review_comment_calls == 1


def test_with_backoff_retries_retryable_errors(monkeypatch) -> None:
	fake_pr = _FakePR(files=[])
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	monkeypatch.setattr("services.github_client.time.sleep", lambda _x: None)

	class RetryableError(Exception):
		status = 429

	attempts = {"count": 0}

	def flaky_operation():
		attempts["count"] += 1
		if attempts["count"] == 1:
			raise RetryableError("rate limit")
		return "ok"

	result = client._with_backoff(flaky_operation)

	assert result == "ok"
	assert attempts["count"] == 2
