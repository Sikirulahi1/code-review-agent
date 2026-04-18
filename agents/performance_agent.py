from __future__ import annotations

from agents.base_specialist import BaseSpecialistAgent
from services.llm_client import LLMClient


class PerformanceAgent(BaseSpecialistAgent):
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		super().__init__(
			prompt_file="performance_agent.txt",
			category="performance",
			task_instruction=(
				"Find performance bottlenecks and scalability risks. "
				"Return JSON list of findings."
			),
			llm_client=llm_client,
		)
