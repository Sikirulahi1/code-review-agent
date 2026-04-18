from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.github_client import GitHubClient


class _FakePR:
	def __init__(
		self,
		files: list[SimpleNamespace],
		sha: str = "abc123",
		fail_review_comment: bool = False,
	) -> None:
		self.head = SimpleNamespace(sha=sha)
		self.base = SimpleNamespace(sha="base123")
		self.title = "Title"
		self.body = "Body"
		self.user = SimpleNamespace(login="user")
		self._files = files
		self._fail_review_comment = fail_review_comment
		self.get_files_calls = 0
		self.review_comment_calls = 0
		self.review_reply_calls = 0
		self.last_review_comment_args: dict[str, object] | None = None
		self.last_review_reply_args: dict[str, object] | None = None

	def get_files(self):
		self.get_files_calls += 1
		return self._files

	def create_review_comment(
		self,
		body,
		commit,
		path,
		line=None,
		side=None,
		start_line=None,
		start_side=None,
		in_reply_to=None,
		subject_type=None,
		as_suggestion=False,
	):
		self.review_comment_calls += 1
		if self._fail_review_comment:
			raise RuntimeError("forced failure")
		self.last_review_comment_args = {
			"body": body,
			"commit": commit,
			"path": path,
			"line": line,
			"side": side,
			"start_line": start_line,
			"start_side": start_side,
			"in_reply_to": in_reply_to,
			"subject_type": subject_type,
			"as_suggestion": as_suggestion,
		}
		return self.last_review_comment_args

	def create_review_comment_reply(self, comment_id: int, body: str):
		self.review_reply_calls += 1
		self.last_review_reply_args = {"comment_id": comment_id, "body": body}
		return self.last_review_reply_args

	def create_review(self, **kwargs):
		return kwargs


class _FakeRepo:
	def __init__(self, pr: _FakePR) -> None:
		self._pr = pr
		self.commit_calls: list[str] = []

	def get_pull(self, _pr_number: int) -> _FakePR:
		return self._pr

	def get_commit(self, sha: str):
		self.commit_calls.append(sha)
		return SimpleNamespace(sha=sha)


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
	assert fake_pr.get_files_calls == 1


def test_queue_and_flush_posts_inline_comments() -> None:
	fake_pr = _FakePR(files=[])
	fake_repo = _FakeRepo(pr=fake_pr)
	client = GitHubClient(github_api=_FakeGithub(repo=fake_repo))

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
	assert fake_repo.commit_calls == ["sha"]
	assert fake_pr.last_review_comment_args is not None
	assert fake_pr.last_review_comment_args["line"] == 3
	assert fake_pr.last_review_comment_args["side"] == "RIGHT"
	assert getattr(fake_pr.last_review_comment_args["commit"], "sha", None) == "sha"


def test_queue_and_flush_posts_reply_comment_when_in_reply_to_is_set() -> None:
	fake_pr = _FakePR(files=[])
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	client.queue_inline_comment(
		repo_full_name="owner/repo",
		pr_number=1,
		body="Reply",
		commit_id="sha",
		path="a.py",
		position=3,
		in_reply_to=42,
	)
	client.flush_comment_queue()

	assert fake_pr.review_reply_calls == 1
	assert fake_pr.review_comment_calls == 0
	assert fake_pr.last_review_reply_args == {"comment_id": 42, "body": "Reply"}


def test_flush_comment_queue_keeps_item_when_post_fails() -> None:
	fake_pr = _FakePR(files=[], fail_review_comment=True)
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	client.queue_inline_comment(
		repo_full_name="owner/repo",
		pr_number=1,
		body="Fail",
		commit_id="sha",
		path="a.py",
		position=3,
	)

	with pytest.raises(RuntimeError):
		client.flush_comment_queue()

	assert len(client._comment_queue) == 1


def test_with_backoff_retries_retryable_errors(monkeypatch) -> None:
	fake_pr = _FakePR(files=[])
	client = GitHubClient(github_api=_FakeGithub(repo=_FakeRepo(pr=fake_pr)))

	monkeypatch.setattr("utils.retry.time.sleep", lambda _x: None)

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
