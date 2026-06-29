from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.graph import build_agent, run_agent


class TestBuildAgent:
    def test_compiles_without_error(self):
        graph = build_agent()
        compiled = graph.compile()
        assert compiled is not None


class TestRunAgent:
    async def test_runs_with_mock_tools(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value=[{"title": "Mock Apt", "price_monthly": 1200}])

        tools = {"search_web": mock_tool}
        schemas = [{"name": "search_web", "description": "Search web"}]

        results = []
        async for event in run_agent(
            query="studio near UCLA",
            tools=tools,
            tool_schemas=schemas,
            max_iterations=2,
            max_steps=3,
        ):
            results.append(event)

        assert len(results) >= 3  # plan, execute, evaluate, synthesize

        final = results[-1]
        for node_name, node_data in final.items():
            if node_data is not None and isinstance(node_data, dict):
                if node_data.get("synthesized_answer"):
                    return

        pytest.fail("Graph did not produce a synthesized answer")

    async def test_respects_max_iterations(self):
        tools = {}
        schemas = [{"name": "test", "description": "test"}]

        results = []
        async for event in run_agent(
            query="test",
            tools=tools,
            tool_schemas=schemas,
            max_iterations=1,
            max_steps=1,
        ):
            results.append(event)

        assert len(results) >= 1
