from __future__ import annotations

from agents.base_specialist import BaseSpecialistAgent
from services.llm_client import LLMClient


class StyleAgent(BaseSpecialistAgent):
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		super().__init__(
			prompt_file="style_agent.txt",
			category="style",
			task_instruction=(
				"Find readability, maintainability, and style issues. "
				"Return JSON list of findings."
			),
			llm_client=llm_client,
		)
