from __future__ import annotations

from services.llm_client import LLMClient


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
