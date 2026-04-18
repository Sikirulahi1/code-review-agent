from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agents.prompt_loader import load_prompt
from services.llm_client import LLMClient


class BaseSpecialistAgent:
    def __init__(
        self,
        *,
        prompt_file: str,
        category: str,
        task_instruction: str,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._prompt_text = load_prompt(prompt_file)
        self._category = category
        self._task_instruction = task_instruction
        self._llm_client = llm_client or LLMClient()

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__.replace("Agent", "").lower()

    def review_file_patch(self, file_path: str, patch: str) -> list[dict[str, Any]]:
        findings = self._llm_client.request_findings_from_diff(
            diff_content=patch,
            system_prompt=self._prompt_text,
            task_instruction=self._task_instruction,
        )

        normalized: list[dict[str, Any]] = []
        for finding in findings:
            normalized.append(
                {
                    **finding,
                    "file_path": finding.get("file_path") or file_path,
                    "category": finding.get("category") or self._category,
                    "agent_name": finding.get("agent_name") or self.agent_name,
                }
            )

        return normalized

    def review_diff_chunks(
        self,
        diff_chunks: Mapping[str, list[str]],
    ) -> list[dict[str, Any]]:
        all_findings: list[dict[str, Any]] = []
        for file_path, chunks in diff_chunks.items():
            for chunk in chunks:
                all_findings.extend(self.review_file_patch(file_path, chunk))
        return all_findings