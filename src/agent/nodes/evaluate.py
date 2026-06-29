from typing import Any

from langgraph.types import RunnableConfig


async def evaluate_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    ctx = config.get("configurable", {}).get("context", {})
    plan = state.get("plan", "")
    step_idx = state.get("step_index", 0)
    results = state.get("results", [])
    iteration = state.get("iteration", 0)
    max_iterations = ctx.get("max_iterations", 5)
    max_steps = state.get("max_steps", 10)

    lines = [ln for ln in plan.split("\n") if ln.strip()]
    all_done = step_idx >= len(lines) or step_idx >= max_steps
    has_data = len(results) > 0

    if iteration >= max_iterations:
        return {"decision": "synthesize", "error": "Max iterations reached"}

    if all_done and has_data:
        return {"decision": "synthesize"}
    if all_done and not has_data:
        return {"decision": "plan", "error": "Plan executed but no results"}

    return {"decision": "execute"}
