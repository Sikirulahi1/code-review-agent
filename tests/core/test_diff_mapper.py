from core.diff_mapper import (
	attach_diff_positions,
	build_line_to_position_map,
	classify_finding_for_comment,
)


def test_build_line_to_position_map_single_hunk() -> None:
	patch = "\n".join(
		[
			"@@ -1,3 +1,4 @@",
			" line1",
			"-line2",
			"+line2a",
			" line3",
			"+line4",
		]
	)

	result = build_line_to_position_map(patch)

	assert result == {2: 3, 4: 5}


def test_build_line_to_position_map_multiple_hunks() -> None:
	patch = "\n".join(
		[
			"@@ -1,2 +1,2 @@",
			"-a",
			"+b",
			" c",
			"@@ -10,2 +10,3 @@",
			" x",
			"-y",
			"+z",
			"+q",
		]
	)

	result = build_line_to_position_map(patch)

	assert result == {1: 2, 11: 6, 12: 7}


def test_build_line_to_position_map_when_lines_shift() -> None:
	patch = "\n".join(
		[
			"@@ -20,3 +30,4 @@",
			" a",
			"-b",
			"+c",
			" d",
			"+e",
		]
	)

	result = build_line_to_position_map(patch)

	assert result == {31: 3, 33: 5}


def test_build_line_to_position_map_deletions_only() -> None:
	patch = "\n".join(
		[
			"@@ -1,2 +0,0 @@",
			"-old_a",
			"-old_b",
		]
	)

	result = build_line_to_position_map(patch)

	assert result == {}


def test_build_line_to_position_map_large_diff() -> None:
	patch_lines = ["@@ -1,1000 +1,1000 @@"]
	patch_lines.extend(f"+line_{index}" for index in range(1, 1001))

	result = build_line_to_position_map("\n".join(patch_lines))

	assert len(result) == 1000
	assert result[1] == 1
	assert result[1000] == 1000


def test_classify_finding_fallback_when_line_unmappable() -> None:
	patch = "\n".join(
		[
			"@@ -1,1 +1,1 @@",
			"-old",
			"+new",
		]
	)
	line_to_position = build_line_to_position_map(patch)

	finding = {
		"file_path": "api/routes/webhook.py",
		"line_start": 99,
	}

	result = classify_finding_for_comment(finding, line_to_position)

	assert result == {
		"diff_position": None,
		"comment_destination": "summary_fallback",
		"mapping_failed": True,
	}


def test_attach_diff_positions_mixed_findings() -> None:
	findings = [
		{"file_path": "a.py", "line_start": 10, "title": "inline"},
		{"file_path": "a.py", "line_start": 11, "title": "fallback"},
		{"file_path": "b.py", "line_start": 1, "title": "missing table"},
	]
	tables = {"a.py": {10: 4}}

	result = attach_diff_positions(findings, tables)

	assert result[0]["comment_destination"] == "inline"
	assert result[0]["diff_position"] == 4
	assert result[0]["mapping_failed"] is False

	assert result[1]["comment_destination"] == "summary_fallback"
	assert result[1]["diff_position"] is None
	assert result[1]["mapping_failed"] is True

	assert result[2]["comment_destination"] == "summary_fallback"
	assert result[2]["diff_position"] is None
	assert result[2]["mapping_failed"] is True
