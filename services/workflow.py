from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.coordinator import CoordinatorAgent
from agents.factory import create_specialist_agent
from agents.supervisor import filter_prompt_injection_findings

from services.nodes import WorkflowNodes
from services.schemas import WorkflowState


class WorkflowService:
	def __init__(
		self,
		*,
		coordinator_agent: CoordinatorAgent | None = None,
		bug_agent=None,
		security_agent=None,
		performance_agent=None,
		style_agent=None,
		supervisor_filter=filter_prompt_injection_findings,
	) -> None:
		self._coordinator_agent = coordinator_agent or CoordinatorAgent()
		self._bug_agent = bug_agent or create_specialist_agent("bug")
		self._security_agent = security_agent or create_specialist_agent("security")
		self._performance_agent = performance_agent or create_specialist_agent("performance")
		self._style_agent = style_agent or create_specialist_agent("style")
		self._supervisor_filter = supervisor_filter
		self._nodes = WorkflowNodes(
			coordinator_agent=self._coordinator_agent,
			bug_agent=self._bug_agent,
			security_agent=self._security_agent,
			performance_agent=self._performance_agent,
			style_agent=self._style_agent,
			supervisor_filter=self._supervisor_filter,
		)
		self._graph = self._build_graph()

	def run_review(self, repo_full_name: str, pr_number: int) -> WorkflowState:
		initial_state: WorkflowState = {
			"repo_full_name": repo_full_name,
			"pr_number": pr_number,
			"errors": [],
		}
		return self._graph.invoke(initial_state)

	def _build_graph(self):
		builder = StateGraph(WorkflowState)
		builder.add_node("coordinator", self._nodes.coordinator)
		builder.add_node("bug", self._nodes.bug)
		builder.add_node("security", self._nodes.security)
		builder.add_node("performance", self._nodes.performance)
		builder.add_node("style", self._nodes.style)
		builder.add_node("supervisor", self._nodes.supervisor)

		builder.add_edge(START, "coordinator")
		builder.add_edge("coordinator", "bug")
		builder.add_edge("coordinator", "security")
		builder.add_edge("coordinator", "performance")
		builder.add_edge("coordinator", "style")
		builder.add_edge("bug", "supervisor")
		builder.add_edge("security", "supervisor")
		builder.add_edge("performance", "supervisor")
		builder.add_edge("style", "supervisor")
		builder.add_edge("supervisor", END)

		return builder.compile()
