from unittest.mock import AsyncMock, MagicMock

from src.agent.nodes.evaluate import evaluate_node
from src.agent.nodes.execute import execute_node, _parse_plan_line
from src.agent.nodes.plan import plan_node
from src.agent.nodes.synthesize import synthesize_node


class TestParsePlanLine:
    def test_parses_simple_call(self):
        result = _parse_plan_line("1. search_web(query=\"studio\", count=10)")
        assert result is not None
        assert result[0] == "search_web"
        assert result[1]["query"] == "studio"

    def test_parses_without_quotes(self):
        result = _parse_plan_line("2. scrape_url(url=$url_1)")
        assert result is not None
        assert result[0] == "scrape_url"

    def test_returns_none_for_invalid_line(self):
        result = _parse_plan_line("invalid line")
        assert result is None


class TestPlanNode:
    async def test_generates_static_plan(self):
        state = {
            "query": "test query",
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "plan" in result
        assert "search_web(query=\"test query\", count=8)" in result["plan"]
        assert result["step_index"] == 0
        assert result["iteration"] == 1


class TestExecuteNode:
    async def test_skips_if_no_more_steps(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 5,
            "results": [],
        }
        config = {"configurable": {"context": {"tools": {}}}}
        result = await execute_node(state, config)
        assert result["step_index"] == 6

    async def test_returns_error_for_unknown_tool(self):
        state = {
            "plan": "1. unknown_tool(x=1)",
            "step_index": 0,
            "results": [],
        }
        config = {"configurable": {"context": {"tools": {}}}}
        result = await execute_node(state, config)
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_calls_tool_and_adds_result(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value=["result1"])

        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 0,
            "results": [],
        }
        config = {"configurable": {"context": {"tools": {"search_web": mock_tool}}}}
        result = await execute_node(state, config)
        assert result["step_index"] == 1
        assert "result1" in result["results"]


class TestEvaluateNode:
    async def test_routes_to_synthesize_when_done(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 1,
            "results": [{"title": "Apt"}],
            "iteration": 1,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "synthesize"

    async def test_routes_to_execute_when_steps_remain(self):
        state = {
            "plan": "1. search_web(query=\"test\")\n2. scrape_url(url=\"x\")",
            "step_index": 0,
            "results": [],
            "iteration": 1,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "execute"

    async def test_routes_to_synthesize_on_max_iterations(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 0,
            "results": [],
            "iteration": 10,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "synthesize"


class TestSynthesizeNode:
    async def test_uses_synthesize_tool_when_available(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value="Found 3 apartments")

        state = {
            "query": "studio",
            "results": [{"title": "Apt"}],
        }
        config = {
            "configurable": {
                "context": {
                    "tools": {"synthesize_answer": mock_tool},
                    "bedrock_client": None,
                }
            }
        }
        result = await synthesize_node(state, config)
        assert result["synthesized_answer"] == "Found 3 apartments"

    async def test_generates_default_when_no_tool(self):
        state = {
            "query": "studio near UCLA",
            "results": [{"title": "Apt 1"}],
        }
        config = {"configurable": {"context": {"tools": {}, "bedrock_client": None}}}
        result = await synthesize_node(state, config)
        assert "studio" in result["synthesized_answer"].lower()
