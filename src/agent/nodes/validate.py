from typing import Any

from langgraph.types import RunnableConfig

from src.guardrails.output.guard import validate_results


async def validate_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state.get("query", "")
    intent = state.get("intent", {})
    results = state.get("results", [])
    ctx = config.get("configurable", {}).get("context", {})
    bedrock = ctx.get("bedrock_client")

    if not results:
        report = {
            "passed": True,
            "issues": [],
            "properties_filtered": 0,
            "pii_stripped": False,
            "method": "noop",
        }
        return {"validation_report": report}

    cleaned, report = await validate_results(
        properties=results,
        query=query,
        intent=intent,
        bedrock_client=bedrock,
    )

    update: dict[str, Any] = {
        "results": cleaned,
        "validation_report": report,
    }

    if not report["passed"] and report["issues"]:
        update["error"] = "; ".join(report["issues"][:3])

    return update
