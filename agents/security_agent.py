from __future__ import annotations

from agents.base_specialist import BaseSpecialistAgent
from services.llm_client import LLMClient


class SecurityAgent(BaseSpecialistAgent):
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		super().__init__(
			prompt_file="security_agent.txt",
			category="security",
			task_instruction=(
				"Find security vulnerabilities and unsafe coding patterns. "
				"Return JSON list of findings."
			),
			llm_client=llm_client,
		)
