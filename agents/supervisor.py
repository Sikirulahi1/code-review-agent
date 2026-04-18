from __future__ import annotations

import re
from typing import Any, Mapping

INJECTION_PATTERNS = [
	r"ignore\s+all\s+previous\s+instructions",
	r"you\s+are\s+now",
	r"do\s+not\s+flag",
	r"system\s+prompt",
	r"developer\s+message",
	r"jailbreak",
]


def looks_like_prompt_injection(text: str) -> bool:
	value = text.lower()
	return any(re.search(pattern, value) for pattern in INJECTION_PATTERNS)


def filter_prompt_injection_findings(
	findings: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
	filtered: list[dict[str, Any]] = []
	for finding in findings:
		payload = " ".join(
			[
				str(finding.get("title") or ""),
				str(finding.get("description") or ""),
				str(finding.get("suggestion") or ""),
			]
		)
		if looks_like_prompt_injection(payload):
			continue
		filtered.append(dict(finding))
	return filtered
