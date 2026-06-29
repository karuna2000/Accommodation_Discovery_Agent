from typing import Any

from langgraph.types import RunnableConfig

from src.mcp.tools.synthesize import _fmt_property


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

    if not results:
        return {"synthesized_answer": f"I couldn't find any properties matching '{query}'. Try refining your search."}

    props = [p for p in results if isinstance(p, dict) and p.get("confidence", 0) >= 0.15]
    if not props:
        props = results[:5] if isinstance(results[0], dict) else []

    if not props:
        plan_text = state.get("plan", "")
        if isinstance(plan_text, list):
            plan_text = "\n".join(plan_text)
        if any(isinstance(r, dict) and r.get("title") and r.get("confidence", 0) >= 0.15 for r in results):
            props = [r for r in results if isinstance(r, dict) and r.get("title")]
        else:
            return {"synthesized_answer": f"I processed your query '{query}' but the scraped data didn't contain structured property details.\n\nPlan used:\n{plan_text}\n\nRaw results:\n" + "\n".join(str(r)[:200] for r in results[:3])}

    lines = [f"Here are {len(props)} properties matching '{query}':", ""]
    for p in props:
        lines.append(_fmt_property(p))
        lines.append("")

    return {"synthesized_answer": "\n".join(lines).strip()}
