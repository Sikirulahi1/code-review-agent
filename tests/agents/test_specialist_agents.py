from agents.bug_agent import BugAgent
from agents.performance_agent import PerformanceAgent
from agents.security_agent import SecurityAgent
from agents.style_agent import StyleAgent


class _FakeLLMClient:
	def __init__(self) -> None:
		self.calls: list[dict[str, str | None]] = []

	def request_findings_from_diff(
		self,
		diff_content: str,
		system_prompt: str,
		task_instruction: str | None = None,
	) -> list[dict[str, object]]:
		self.calls.append(
			{
				"diff_content": diff_content,
				"system_prompt": system_prompt,
				"task_instruction": task_instruction,
			}
		)
		return [
			{
				"title": "Issue",
				"description": "Details",
				"severity": 3,
			}
		]


def _assert_specialist_behavior(agent, expected_category: str) -> None:
	findings = agent.review_file_patch("api/routes/webhook.py", "+print('x')")
	assert len(findings) == 1
	assert findings[0]["file_path"] == "api/routes/webhook.py"
	assert findings[0]["category"] == expected_category
	assert findings[0]["agent_name"]


def test_bug_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = BugAgent(llm_client=llm)
	_assert_specialist_behavior(agent, "bug")


def test_security_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = SecurityAgent(llm_client=llm)
	_assert_specialist_behavior(agent, "security")


def test_performance_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = PerformanceAgent(llm_client=llm)
	_assert_specialist_behavior(agent, "performance")


def test_style_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = StyleAgent(llm_client=llm)
	_assert_specialist_behavior(agent, "style")


def test_review_diff_chunks_calls_llm_for_each_chunk() -> None:
	llm = _FakeLLMClient()
	agent = BugAgent(llm_client=llm)

	findings = agent.review_diff_chunks(
		{
			"a.py": ["+line_a", "+line_b"],
			"b.py": ["+line_c"],
		}
	)

	assert len(llm.calls) == 3
	assert len(findings) == 3
