from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from github import Github

from config import settings
from utils.retry import run_with_exponential_backoff

LOGGER = logging.getLogger(__name__)


@dataclass
class QueuedComment:
	repo_full_name: str
	pr_number: int
	body: str
	commit_id: str
	path: str
	position: int
	in_reply_to: int | None = None


class GitHubClient:
	def __init__(self, github_api: Any | None = None) -> None:
		token = settings.github_token.get_secret_value() if settings.github_token else None
		self._github = github_api or Github(token)
		self._diff_cache: dict[str, dict[str, str]] = {}
		self._comment_queue: deque[QueuedComment] = deque()
		self._retry_attempts = max(1, settings.github_retry_attempts)
		self._backoff_max_seconds = max(1, settings.comment_backoff_max_seconds)

	def get_pr_metadata(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
		repo = self._github.get_repo(repo_full_name)
		pr = repo.get_pull(pr_number)
		return {
			"title": pr.title,
			"description": pr.body or "",
			"author": pr.user.login,
			"head_sha": pr.head.sha,
			"base_sha": pr.base.sha,
		}

	def fetch_pr_patches(self, repo_full_name: str, pr_number: int) -> dict[str, str]:
		repo = self._github.get_repo(repo_full_name)
		pr = repo.get_pull(pr_number)
		cache_key = f"{repo_full_name}#{pr_number}@{pr.head.sha}"
		if cache_key in self._diff_cache:
			return self._diff_cache[cache_key]

		patches = {file.filename: (file.patch or "") for file in pr.get_files()}
		self._diff_cache[cache_key] = patches
		return patches

	def queue_inline_comment(
		self,
		repo_full_name: str,
		pr_number: int,
		body: str,
		commit_id: str,
		path: str,
		position: int,
		in_reply_to: int | None = None,
	) -> None:
		self._comment_queue.append(
			QueuedComment(
				repo_full_name=repo_full_name,
				pr_number=pr_number,
				body=body,
				commit_id=commit_id,
				path=path,
				position=position,
				in_reply_to=in_reply_to,
			)
		)

	def flush_comment_queue(self) -> None:
		while self._comment_queue:
			queued = self._comment_queue[0]
			self._with_backoff(lambda: self._post_inline_comment_now(queued))
			self._comment_queue.popleft()

	def create_summary_review(
		self,
		repo_full_name: str,
		pr_number: int,
		body: str,
		event: str = "COMMENT",
	) -> Any:
		return self._with_backoff(
			lambda: self._create_summary_review_now(repo_full_name, pr_number, body, event)
		)

	def _post_inline_comment_now(self, queued: QueuedComment) -> Any:
		repo = self._github.get_repo(queued.repo_full_name)
		pr = repo.get_pull(queued.pr_number)

		if queued.in_reply_to is not None:
			return pr.create_review_comment_reply(queued.in_reply_to, queued.body)

		commit = repo.get_commit(queued.commit_id)
		return pr.create_review_comment(
			body=queued.body,
			commit=commit,
			path=queued.path,
			line=queued.position,
			side="RIGHT",
		)

	def _create_summary_review_now(
		self,
		repo_full_name: str,
		pr_number: int,
		body: str,
		event: str,
	) -> Any:
		repo = self._github.get_repo(repo_full_name)
		pr = repo.get_pull(pr_number)
		return pr.create_review(body=body, event=event)

	def _with_backoff(self, operation: Callable[[], Any]) -> Any:
		return run_with_exponential_backoff(
			operation,
			retry_attempts=self._retry_attempts,
			backoff_max_seconds=float(self._backoff_max_seconds),
			should_retry=self._should_retry,
			logger=LOGGER,
			retry_log_template="GitHub write retry in %ss (attempt %s)",
		)

	@staticmethod
	def _should_retry(exc: Exception) -> bool:
		status = getattr(exc, "status", None)
		if status in {403, 429, 500, 502, 503, 504}:
			return True

		message = str(exc).lower()
		return "rate limit" in message or "tempor" in message
