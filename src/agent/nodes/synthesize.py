from typing import Any

from langgraph.types import RunnableConfig


async def synthesize_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state.get("query", "")
    results = state.get("results", [])
    ctx = config.get("configurable", {}).get("context", {})
    bedrock = ctx.get("bedrock_client")
    tools = ctx.get("tools", {})

    synth_tool = tools.get("synthesize_answer")
    if synth_tool:
        try:
            answer = await synth_tool.run(properties=results, query=query)
            return {"synthesized_answer": answer}
        except Exception:
            pass

    if bedrock:
        try:
            answer = await bedrock.synthesize(results, query)
            return {"synthesized_answer": answer}
        except Exception:
            pass

    count = len(results)
    answer = (
        f"I found {count} properties matching '{query}'. "
        f"Here's a summary of the best options available."
    )
    return {"synthesized_answer": answer}
