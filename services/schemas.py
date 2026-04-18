from __future__ import annotations

from operator import add
from typing import Any, Annotated, TypedDict


class WorkflowState(TypedDict, total=False):
	repo_full_name: str
	pr_number: int
	pr_metadata: dict[str, Any]
	pr_context: dict[str, Any]
	diff_chunks: dict[str, list[str]]
	position_tables: dict[str, dict[int, int]]
	chunking_strategy: dict[str, str]
	bug_findings: list[dict[str, Any]]
	security_findings: list[dict[str, Any]]
	performance_findings: list[dict[str, Any]]
	style_findings: list[dict[str, Any]]
	raw_findings: list[dict[str, Any]]
	deduped_findings: list[dict[str, Any]]
	final_findings: list[dict[str, Any]]
	summary: dict[str, int]
	errors: Annotated[list[str], add]
