from __future__ import annotations

import re
from typing import Any, Mapping

HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def build_line_to_position_map(patch: str) -> dict[int, int]:
	"""Map new-file line numbers to GitHub diff positions for added lines only."""
	if not patch:
		return {}

	line_to_position: dict[int, int] = {}
	position = 0
	current_new_line: int | None = None

	for line in patch.splitlines():
		hunk_match = HUNK_HEADER_RE.match(line)
		if hunk_match:
			current_new_line = int(hunk_match.group(1))
			continue

		if current_new_line is None or line.startswith("\\ No newline at end of file"):
			continue

		position += 1
		marker = line[:1]

		if marker == "+":
			line_to_position[current_new_line] = position
			current_new_line += 1
		elif marker == " ":
			current_new_line += 1
		elif marker == "-":
			continue

	return line_to_position


def classify_finding_for_comment(
	finding: Mapping[str, Any],
	line_to_position: Mapping[int, int],
) -> dict[str, Any]:
	"""Return mapping fields that determine inline vs summary destination."""
	line_start = finding.get("line_start")

	if isinstance(line_start, int) and line_start in line_to_position:
		return {
			"diff_position": line_to_position[line_start],
			"comment_destination": "inline",
			"mapping_failed": False,
		}

	return {
		"diff_position": None,
		"comment_destination": "summary_fallback",
		"mapping_failed": True,
	}


def attach_diff_positions(
	findings: list[Mapping[str, Any]],
	position_tables: Mapping[str, Mapping[int, int]],
) -> list[dict[str, Any]]:
	"""Attach mapping fields to each finding based on its file and line_start."""
	mapped_findings: list[dict[str, Any]] = []

	for finding in findings:
		file_path = str(finding.get("file_path") or "")
		line_to_position = position_tables.get(file_path, {})
		mapping_fields = classify_finding_for_comment(finding, line_to_position)
		mapped_findings.append({**finding, **mapping_fields})

	return mapped_findings
