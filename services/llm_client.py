from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import google.generativeai as genai
from openai import OpenAI

from config import settings
from utils.llm_payload import parse_findings_payload
from utils.retry import run_with_exponential_backoff

LOGGER = logging.getLogger(__name__)


class LLMClient:
	def __init__(self, openai_client: Any | None = None) -> None:
		self._gemini_api_key = (
			settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
		)
		self._openai_api_key = (
			settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
		)
		self._gemini_model = settings.gemini_model
		self._openai_model = settings.openai_model
		self._timeout_seconds = max(1, settings.llm_timeout_seconds)
		self._retry_attempts = max(1, settings.llm_retry_attempts)
		self._backoff_max_seconds = max(1, settings.llm_backoff_max_seconds)
		self._openai = openai_client or (
			OpenAI(api_key=self._openai_api_key) if self._openai_api_key else None
		)

		if self._gemini_api_key:
			genai.configure(api_key=self._gemini_api_key)

	def request_text(self, user_content: str, system_prompt: str | None = None) -> str:
		try:
			return self._retry(lambda: self._call_gemini(user_content, system_prompt))
		except Exception as gemini_exc:
			LOGGER.warning("Gemini failed, falling back to OpenAI: %s", gemini_exc)
			return self._retry(lambda: self._call_openai(user_content, system_prompt))

	def request_findings(
		self,
		user_content: str,
		system_prompt: str | None = None,
	) -> list[dict[str, Any]]:
		try:
			response_text = self.request_text(user_content, system_prompt)
			return parse_findings_payload(response_text)
		except Exception as exc:
			LOGGER.warning("LLM request failed; returning empty findings: %s", exc)
			return []

	def _call_gemini(self, user_content: str, system_prompt: str | None = None) -> str:
		if not self._gemini_api_key:
			raise RuntimeError("GEMINI_API_KEY is not configured")

		model = genai.GenerativeModel(
			model_name=self._gemini_model,
			system_instruction=system_prompt,
		)
		response = model.generate_content(
			user_content,
			request_options={"timeout": self._timeout_seconds},
		)
		text = getattr(response, "text", None)
		if not text:
			raise RuntimeError("Gemini returned an empty response")
		return text

	def _call_openai(self, user_content: str, system_prompt: str | None = None) -> str:
		if not self._openai:
			raise RuntimeError("OPENAI_API_KEY is not configured")

		messages: list[dict[str, str]] = []
		if system_prompt:
			messages.append({"role": "system", "content": system_prompt})
		messages.append({"role": "user", "content": user_content})

		response = self._openai.chat.completions.create(
			model=self._openai_model,
			messages=messages,
			timeout=self._timeout_seconds,
		)
		text = response.choices[0].message.content
		if not text:
			raise RuntimeError("OpenAI returned an empty response")
		return text

	def _retry(self, operation: Callable[[], str]) -> str:
		return run_with_exponential_backoff(
			operation,
			retry_attempts=self._retry_attempts,
			backoff_max_seconds=float(self._backoff_max_seconds),
			should_retry=self._should_retry,
			jitter_max_seconds=0.25,
		)

	@staticmethod
	def _should_retry(exc: Exception) -> bool:
		message = str(exc).lower()
		retry_terms = ["rate limit", "timeout", "tempor", "503", "429", "resourceexhausted"]
		return any(term in message for term in retry_terms)
