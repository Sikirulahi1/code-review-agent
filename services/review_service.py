from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import logging

from sqlalchemy import desc, select

from core.fingerprint import generate_fingerprint
from core.formatter import Formatter
from db import Finding, Review, session_factory
from services.workflow import WorkflowService

logger = logging.getLogger(__name__)

def _utc_iso_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def _split_repo_full_name(repo_full_name: str) -> tuple[str, str]:
	parts = repo_full_name.split("/", maxsplit=1)
	if len(parts) == 2 and parts[0] and parts[1]:
		return parts[0], parts[1]
	return repo_full_name, "unknown"


def _int_or_none(value: Any) -> int | None:
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	try:
		parsed = int(str(value))
	except (TypeError, ValueError):
		return None
	return parsed


def _normalize_severity(value: Any) -> int:
	severity = _int_or_none(value)
	if severity is None:
		return 3
	return max(1, min(5, severity))


def _normalize_confidence(value: Any) -> float | None:
	if value is None:
		return None
	try:
		confidence = float(value)
	except (TypeError, ValueError):
		return None
	if confidence < 0.0:
		return 0.0
	if confidence > 1.0:
		return 1.0
	return confidence


class ReviewService:
	def __init__(self, workflow_service: WorkflowService | None = None) -> None:
		self._workflow_service = workflow_service or WorkflowService()

	async def run_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
		logger.info(f"Starting review process for PR {pr_number} on {repo_full_name}")
		state = self._workflow_service.run_review(repo_full_name, pr_number)
		logger.info(f"Workflow finished for PR {pr_number}")

		raw_findings = list(state.get("final_findings", []))
		
		for f in raw_findings:
			if not f.get("fingerprint"):
				f["fingerprint"] = generate_fingerprint(f)
		
		# Incremental tracking
		prior_review = await self.get_latest_review(repo_full_name, pr_number)
		prior_findings = prior_review.get("findings", []) if prior_review else []
		
		from core.incremental import classify_findings
		classification = classify_findings(raw_findings, prior_findings)
		tracked_findings = classification["new"] + classification["persisted"] + classification["resolved"]

		formatted_findings = []
		for f in tracked_findings:
			nf = dict(f)
			nf["markdown_body"] = Formatter.build_inline_comment(f)
			formatted_findings.append(nf)

		result: dict[str, Any] = {
			"repo_full_name": repo_full_name,
			"pr_number": pr_number,
			"reviewed_at": _utc_iso_now(),
			"pr_metadata": state.get("pr_metadata", {}),
			"summary": state.get(
				"summary",
				{"raw_count": 0, "deduped_count": 0, "final_count": 0},
			),
			"errors": list(state.get("errors", [])),
			"findings": formatted_findings,
			"markdown_preview": {
				"summary_comment": Formatter.build_summary_comment(tracked_findings, state.get("pr_metadata")),
			},
		}

		await self._persist_result(result)
		return result

	async def get_latest_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any] | None:
		return await self._load_latest_review(repo_full_name, pr_number)

	async def _load_latest_review(self, repo_full_name: str, pr_number: int) -> dict[str, Any] | None:
		repo_owner, repo_name = _split_repo_full_name(repo_full_name)

		async with session_factory() as session:
			review_statement = (
				select(Review)
				.where(
					Review.repo_owner == repo_owner,
					Review.repo_name == repo_name,
					Review.pr_number == pr_number,
				)
				.order_by(desc(Review.created_at), desc(Review.id))
				.limit(1)
			)
			review_result = await session.execute(review_statement)
			review = review_result.scalars().first()
			if not review:
				return None

			findings_statement = (
				select(Finding)
				.where(Finding.review_id == review.id)
				.order_by(Finding.id)
			)
			findings_result = await session.execute(findings_statement)
			findings = findings_result.scalars().all()

			loaded_findings = [self._finding_to_payload(item) for item in findings]
			formatted_findings = []
			for f in loaded_findings:
				nf = dict(f)
				nf["markdown_body"] = Formatter.build_inline_comment(f)
				formatted_findings.append(nf)

			return {
				"repo_full_name": f"{review.repo_owner}/{review.repo_name}",
				"pr_number": review.pr_number,
				"reviewed_at": review.created_at.isoformat(),
				"pr_metadata": {"head_sha": review.commit_sha},
				"summary": {
					"raw_count": review.total_findings,
					"deduped_count": review.total_findings,
					"final_count": review.total_findings,
				},
				"errors": [],
				"findings": formatted_findings,
				"markdown_preview": {
					"summary_comment": Formatter.build_summary_comment(loaded_findings, {"head_sha": review.commit_sha})
				},
			}

	async def _persist_result(self, result: dict[str, Any]) -> None:
		repo_full_name = str(result.get("repo_full_name") or "")
		repo_owner, repo_name = _split_repo_full_name(repo_full_name)
		pr_number = _int_or_none(result.get("pr_number")) or 0
		pr_metadata = result.get("pr_metadata", {})
		commit_sha = str((pr_metadata or {}).get("head_sha") or "unknown")[:64]
		summary = result.get("summary", {})
		findings = list(result.get("findings", []))
		total_findings = _int_or_none((summary or {}).get("final_count")) or len(findings)

		async with session_factory() as session:
			review = Review(
				repo_owner=repo_owner,
				repo_name=repo_name,
				pr_number=pr_number,
				commit_sha=commit_sha,
				recommendation=None,
				total_findings=total_findings,
			)
			session.add(review)
			await session.flush()

			for finding in findings:
				normalized_finding = dict(finding)
				fingerprint = generate_fingerprint(normalized_finding)
				diff_position = _int_or_none(normalized_finding.get("diff_position"))
				comment_destination = str(
					normalized_finding.get("comment_destination")
					or ("inline" if diff_position is not None else "summary_fallback")
				)

				session.add(
					Finding(
						review_id=review.id,
						agent_name=str(normalized_finding.get("agent_name") or "unknown"),
						category=str(normalized_finding.get("category") or "unknown"),
						severity=_normalize_severity(normalized_finding.get("severity")),
						original_severity=_int_or_none(
							normalized_finding.get("original_severity")
						),
						confidence=_normalize_confidence(normalized_finding.get("confidence")),
						title=str(normalized_finding.get("title") or "Untitled finding")[:500],
						description=str(normalized_finding.get("description") or ""),
						suggestion=(
							str(normalized_finding.get("suggestion"))
							if normalized_finding.get("suggestion") is not None
							else None
						),
						code_fix=(
							str(normalized_finding.get("code_fix"))
							if normalized_finding.get("code_fix") is not None
							else None
						),
						file_path=str(normalized_finding.get("file_path") or ""),
						line_start=_int_or_none(normalized_finding.get("line_start")),
						line_end=_int_or_none(normalized_finding.get("line_end")),
						fingerprint=fingerprint,
						diff_position=diff_position,
						comment_destination=comment_destination[:32],
						mapping_failed=bool(
							normalized_finding.get("mapping_failed", diff_position is None)
						),
						github_comment_id=_int_or_none(
							normalized_finding.get("github_comment_id")
						),
						status=str(normalized_finding.get("status") or "open")[:32],
					)
				)

			await session.commit()

	def _finding_to_payload(self, finding: Finding) -> dict[str, Any]:
		return {
			"id": finding.id,
			"agent_name": finding.agent_name,
			"category": finding.category,
			"severity": finding.severity,
			"original_severity": finding.original_severity,
			"confidence": finding.confidence,
			"title": finding.title,
			"description": finding.description,
			"suggestion": finding.suggestion,
			"code_fix": finding.code_fix,
			"file_path": finding.file_path,
			"line_start": finding.line_start,
			"line_end": finding.line_end,
			"fingerprint": finding.fingerprint,
			"diff_position": finding.diff_position,
			"comment_destination": finding.comment_destination,
			"mapping_failed": finding.mapping_failed,
			"github_comment_id": finding.github_comment_id,
			"status": finding.status,
		}


review_service = ReviewService()
