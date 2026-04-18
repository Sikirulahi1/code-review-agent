from __future__ import annotations

from typing import Literal

from agents.base_specialist import BaseSpecialistAgent
from services.llm_client import LLMClient

AgentType = Literal["bug", "security", "performance", "style"]

_AGENT_CONFIGS = {
    "bug": {
        "prompt_file": "bug_agent.txt",
        "task_instruction": "Find logic bugs, reliability defects, and edge-case failures. Return JSON list of findings.",
    },
    "security": {
        "prompt_file": "security_agent.txt",
        "task_instruction": "Find security vulnerabilities and unsafe coding patterns. Return JSON list of findings.",
    },
    "performance": {
        "prompt_file": "performance_agent.txt",
        "task_instruction": "Find performance bottlenecks and scalability risks. Return JSON list of findings.",
    },
    "style": {
        "prompt_file": "style_agent.txt",
        "task_instruction": "Find readability, maintainability, and style issues. Return JSON list of findings.",
    }
}

def create_specialist_agent(agent_type: AgentType, llm_client: LLMClient | None = None) -> BaseSpecialistAgent:
    """Factory method to create specialist agents based on type."""
    config = _AGENT_CONFIGS[agent_type]
    
    # We must explicitly set agent_name logic since BaseSpecialistAgent expects __class__.__name__ by default
    agent = BaseSpecialistAgent(
        prompt_file=config["prompt_file"],
        category=agent_type,
        task_instruction=config["task_instruction"],
        llm_client=llm_client,
    )
    # Dynamically inject the agent name to avoid getting "basespecialist" for everyone
    agent._forced_agent_name = agent_type
    return agent
