from agents.factory import create_specialist_agent

class _FakeLLMClient:
	def __init__(self) -> None:
		self.calls: list[dict[str, str | None]] = []

	def request_text(
		self,
		user_content: str,
		system_prompt: str | None = None,
	) -> str:
		self.calls.append(
			{
				"user_content": user_content,
				"system_prompt": system_prompt,
			}
		)
		return '[{"title": "Issue", "description": "Details", "severity": 3}]'


def _assert_specialist_behavior(agent, expected_category: str) -> None:
	findings = agent.review_file_patch("api/routes/webhook.py", "+print('x')")
	assert len(findings) == 1
	assert findings[0]["file_path"] == "api/routes/webhook.py"
	assert findings[0]["category"] == expected_category
	assert findings[0]["agent_name"]


def test_bug_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("bug", llm_client=llm)
	_assert_specialist_behavior(agent, "bug")


def test_security_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("security", llm_client=llm)
	_assert_specialist_behavior(agent, "security")


def test_performance_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("performance", llm_client=llm)
	_assert_specialist_behavior(agent, "performance")


def test_style_agent_adds_default_category_and_file_path() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("style", llm_client=llm)
	_assert_specialist_behavior(agent, "style")


def test_review_diff_chunks_calls_llm_for_each_chunk() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("bug", llm_client=llm)

	findings = agent.review_diff_chunks(
		{
			"a.py": ["+line_a", "+line_b"],
			"b.py": ["+line_c"],
		}
	)

	assert len(llm.calls) == 3
	assert len(findings) == 3


def test_specialist_wraps_diff_before_request_text_call() -> None:
	llm = _FakeLLMClient()
	agent = create_specialist_agent("bug", llm_client=llm)

	findings = agent.review_file_patch("a.py", "+print('x')")

	assert len(findings) == 1
	assert len(llm.calls) == 1
	assert llm.calls[0]["system_prompt"] is not None
	assert "<diff>" in str(llm.calls[0]["user_content"])
	assert "</diff>" in str(llm.calls[0]["user_content"])
