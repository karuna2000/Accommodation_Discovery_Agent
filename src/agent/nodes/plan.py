from typing import Any

from langgraph.types import RunnableConfig


async def plan_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state["query"]
    iteration = state.get("iteration", 0)
    results = state.get("results", [])
    ctx = config.get("configurable", {}).get("context", {})
    bedrock = ctx.get("bedrock_client")

    tool_schemas = ctx.get("tool_schemas", [])
    tools_str = "\n".join(
        f"- {t['name']}: {t['description']}" for t in tool_schemas
    )

    existing = ""
    if results:
        existing = (
            f"\nPreviously found {len(results)} properties. "
            "If they are sufficient, end the plan. "
            "If more data is needed, add steps."
        )

    prompt = (
        f"User query: {query}\n\n"
        f"Available tools:\n{tools_str}{existing}\n\n"
        f"Create a numbered plan (one tool call per line) to find accommodation listings. "
        f"Each line: N. tool_name(arg1=value1, arg2=value2)\n"
        f"Start with search_web, then scrape_url for each result, then extract_property. "
        f"Max {state.get('max_steps', 5)} steps.\n"
        f"Return ONLY the plan."
    )

    if bedrock:
        plan_text = await bedrock.invoke_with_fallback(prompt, max_tokens=500)
    else:
        plan_text = (
            f"1. search_web(query=\"{query}\", count=5)\n"
            f"2. scrape_url(url=\"$result_url_1\")\n"
            f"3. extract_property(markdown=\"$markdown_1\", source_url=\"$url_1\")\n"
        )

    return {
        "plan": plan_text.strip(),
        "step_index": 0,
        "iteration": iteration + 1,
    }
