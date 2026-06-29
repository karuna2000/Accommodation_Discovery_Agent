from typing import Any

from langgraph.types import RunnableConfig


async def plan_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state["query"]
    iteration = state.get("iteration", 0)

    plan_text = (
        f"1. search_web(query=\"{query}\", count=8)\n"
        f"2. scrape_url(url=\"$result_url_1\")\n"
        f"3. scrape_url(url=\"$result_url_1_2\")\n"
        f"4. extract_property(markdown=\"$markdown_2\", source_url=\"$result_url_1\")\n"
        f"5. extract_property(markdown=\"$markdown_3\", source_url=\"$result_url_1_2\")\n"
    )

    return {
        "plan": plan_text.strip(),
        "step_index": 0,
        "iteration": iteration + 1,
    }
