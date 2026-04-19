from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableLambda

from agents.coordinator import CoordinatorAgent
from agents.supervisor import filter_prompt_injection_findings
from services.schemas import WorkflowState


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _dedup_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []

    for finding in findings:
        key = (
            _normalize_text(finding.get("file_path")),
            _normalize_text(finding.get("title")),
            _normalize_text(finding.get("description")),
            _normalize_text(finding.get("category")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(finding))

    return unique


class WorkflowNodes:
    def __init__(
        self,
        *,
        coordinator_agent: CoordinatorAgent,
        bug_agent: Any,
        security_agent: Any,
        performance_agent: Any,
        style_agent: Any,
        supervisor_filter=filter_prompt_injection_findings,
    ) -> None:
        self._coordinator_agent = coordinator_agent
        self._bug_agent = bug_agent
        self._security_agent = security_agent
        self._performance_agent = performance_agent
        self._style_agent = style_agent
        self._supervisor_filter = supervisor_filter

        self.coordinator = RunnableLambda(self._coordinator_node)
        self.bug = RunnableLambda(self._bug_node)
        self.security = RunnableLambda(self._security_node)
        self.performance = RunnableLambda(self._performance_node)
        self.style = RunnableLambda(self._style_node)
        self.supervisor = RunnableLambda(self._supervisor_node)

    def _coordinator_node(self, state: WorkflowState) -> WorkflowState:
        repo_full_name = state.get("repo_full_name")
        pr_number = state.get("pr_number")
        if not repo_full_name or pr_number is None:
            raise RuntimeError("Workflow missing repo_full_name or pr_number")

        try:
            prepared_state = self._coordinator_agent.prepare_state(repo_full_name, int(pr_number))
        except Exception as exc:
            raise RuntimeError(f"Coordinator stage failed: {exc}") from exc

        diff_chunks = prepared_state.get("diff_chunks")
        if diff_chunks is None or not isinstance(diff_chunks, dict):
            raise RuntimeError("Coordinator stage failed: invalid diff chunks")

        return {
            "pr_metadata": prepared_state.get("pr_metadata", {}),
            "pr_context": prepared_state.get("_pr_context", {}),
            "diff_chunks": diff_chunks,
            "position_tables": prepared_state.get("position_tables", {}),
            "chunking_strategy": prepared_state.get("chunking_strategy", {}),
            "errors": [str(item) for item in (prepared_state.get("errors") or [])],
        }

    def _bug_node(self, state: WorkflowState) -> WorkflowState:
        return self._run_specialist_node(
            state=state,
            agent_label="bug",
            agent=self._bug_agent,
            result_key="bug_findings",
        )

    def _security_node(self, state: WorkflowState) -> WorkflowState:
        return self._run_specialist_node(
            state=state,
            agent_label="security",
            agent=self._security_agent,
            result_key="security_findings",
        )

    def _performance_node(self, state: WorkflowState) -> WorkflowState:
        return self._run_specialist_node(
            state=state,
            agent_label="performance",
            agent=self._performance_agent,
            result_key="performance_findings",
        )

    def _style_node(self, state: WorkflowState) -> WorkflowState:
        return self._run_specialist_node(
            state=state,
            agent_label="style",
            agent=self._style_agent,
            result_key="style_findings",
        )

    def _run_specialist_node(
        self,
        *,
        state: WorkflowState,
        agent_label: str,
        agent: Any,
        result_key: str,
    ) -> WorkflowState:
        try:
            diff_chunks = state.get("diff_chunks", {})
            findings = agent.review_diff_chunks(diff_chunks)
            return {result_key: findings}
        except Exception as exc:
            return {
                result_key: [],
                "errors": [f"{agent_label} agent failed: {exc}"],
            }

    def _supervisor_node(self, state: WorkflowState) -> WorkflowState:
        raw_findings = [
            *state.get("bug_findings", []),
            *state.get("security_findings", []),
            *state.get("performance_findings", []),
            *state.get("style_findings", []),
        ]

        deduped_findings = _dedup_findings(raw_findings)
        final_findings = self._supervisor_filter(deduped_findings)

        return {
            "raw_findings": raw_findings,
            "deduped_findings": deduped_findings,
            "final_findings": final_findings,
            "summary": {
                "raw_count": len(raw_findings),
                "deduped_count": len(deduped_findings),
                "final_count": len(final_findings),
            },
        }
