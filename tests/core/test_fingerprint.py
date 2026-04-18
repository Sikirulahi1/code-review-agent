from core.fingerprint import generate_fingerprint


def test_fingerprint_is_stable_when_line_numbers_shift() -> None:
	base_finding = {
		"file_path": "api/routes/webhook.py",
		"category": "bug",
		"title": "Possible None access in payload parsing",
		"description": "payload.get('pull_request') may be None before nested access",
		"line_start": 18,
		"line_end": 20,
	}

	shifted_finding = {
		**base_finding,
		"line_start": 28,
		"line_end": 30,
	}

	assert generate_fingerprint(base_finding) == generate_fingerprint(shifted_finding)


def test_fingerprint_differs_for_distinct_findings_on_same_line() -> None:
	finding_one = {
		"file_path": "services/github_client.py",
		"category": "security",
		"title": "Hardcoded token in request headers",
		"description": "Authorization header contains a raw secret token",
		"line_start": 42,
		"line_end": 42,
	}
	finding_two = {
		"file_path": "services/github_client.py",
		"category": "performance",
		"title": "Repeated API call in loop",
		"description": "The same endpoint is called for each item in the list",
		"line_start": 42,
		"line_end": 42,
	}

	assert generate_fingerprint(finding_one) != generate_fingerprint(finding_two)
