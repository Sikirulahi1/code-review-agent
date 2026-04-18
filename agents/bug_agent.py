from __future__ import annotations

from agents.base_specialist import BaseSpecialistAgent
from services.llm_client import LLMClient


class BugAgent(BaseSpecialistAgent):
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		super().__init__(
			prompt_file="bug_agent.txt",
			category="bug",
			task_instruction=(
				"Find logic bugs, reliability defects, and edge-case failures. "
				"Return JSON list of findings."
			),
			llm_client=llm_client,
		)
