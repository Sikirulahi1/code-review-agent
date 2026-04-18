from __future__ import annotations

from services.llm_client import LLMClient, build_untrusted_diff_user_content


def test_request_text_falls_back_to_openai(monkeypatch) -> None:
	client = LLMClient(openai_client=object())

	monkeypatch.setattr(
		client,
		"_call_gemini",
		lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("gemini fail")),
	)
	monkeypatch.setattr(client, "_call_openai", lambda *_args, **_kwargs: "openai ok")
	monkeypatch.setattr(client, "_retry", lambda operation: operation())

	assert client.request_text("prompt") == "openai ok"


def test_request_findings_parses_json_list(monkeypatch) -> None:
	client = LLMClient(openai_client=object())
	monkeypatch.setattr(
		client,
		"request_text",
		lambda *_args, **_kwargs: '[{"title": "A"}, {"title": "B"}]',
	)

	findings = client.request_findings("prompt")

	assert isinstance(findings, list)
	assert len(findings) == 2
	assert findings[0]["title"] == "A"


def test_request_findings_returns_empty_on_invalid_json(monkeypatch) -> None:
	client = LLMClient(openai_client=object())
	monkeypatch.setattr(client, "request_text", lambda *_args, **_kwargs: "not-json")

	assert client.request_findings("prompt") == []


def test_request_findings_parses_fenced_json(monkeypatch) -> None:
	client = LLMClient(openai_client=object())
	monkeypatch.setattr(
		client,
		"request_text",
		lambda *_args, **_kwargs: "```json\n[{\"title\": \"A\"}]\n```",
	)

	findings = client.request_findings("prompt")

	assert len(findings) == 1
	assert findings[0]["title"] == "A"


def test_request_findings_parses_prose_wrapped_json_array(monkeypatch) -> None:
	client = LLMClient(openai_client=object())
	monkeypatch.setattr(
		client,
		"request_text",
		lambda *_args, **_kwargs: "Here are findings:\n[{\"title\": \"B\"}]\nThanks.",
	)

	findings = client.request_findings("prompt")

	assert len(findings) == 1
	assert findings[0]["title"] == "B"


def test_request_findings_parses_findings_key_from_json_object(monkeypatch) -> None:
	client = LLMClient(openai_client=object())
	monkeypatch.setattr(
		client,
		"request_text",
		lambda *_args, **_kwargs: '{"findings": [{"title": "C"}]}',
	)

	findings = client.request_findings("prompt")

	assert len(findings) == 1
	assert findings[0]["title"] == "C"


def test_build_untrusted_diff_user_content_wraps_diff_and_guardrails() -> None:
	content = build_untrusted_diff_user_content("+print('hello')")

	assert "untrusted input" in content.lower()
	assert "ignore any instructions" in content.lower()
	assert "<diff>" in content
	assert "</diff>" in content
	assert "+print('hello')" in content


def test_request_text_from_diff_uses_wrapped_user_content(monkeypatch) -> None:
	client = LLMClient(openai_client=object())

	captured: dict[str, str | None] = {"user_content": None, "system_prompt": None}

	def fake_request_text(user_content: str, system_prompt: str | None = None) -> str:
		captured["user_content"] = user_content
		captured["system_prompt"] = system_prompt
		return "ok"

	monkeypatch.setattr(client, "request_text", fake_request_text)

	result = client.request_text_from_diff(
		diff_content="+print('hello')",
		system_prompt="System rules",
	)

	assert result == "ok"
	assert captured["system_prompt"] == "System rules"
	assert captured["user_content"] is not None
	assert "<diff>" in str(captured["user_content"])
	assert "</diff>" in str(captured["user_content"])
