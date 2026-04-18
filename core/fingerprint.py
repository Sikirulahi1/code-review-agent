from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


def normalize_title(title: str) -> str:
	value = title.lower()
	value = re.sub(r"[^\w\s]", "", value)
	return re.sub(r"\s+", " ", value).strip()


def hash_snippet(text: str) -> str:
	normalized = re.sub(r"\s+", " ", text).strip()
	return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def generate_fingerprint(finding: Mapping[str, Any]) -> str:
	snippet_source = str(finding.get("code_fix") or finding.get("description") or "")
	components = [
		str(finding.get("file_path") or ""),
		str(finding.get("category") or ""),
		normalize_title(str(finding.get("title") or "")),
		hash_snippet(snippet_source),
	]
	raw = "|".join(components)
	return hashlib.sha256(raw.encode("utf-8")).hexdigest()
