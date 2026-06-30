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
    constraint_tier = state.get("constraint_tier", 0)

    lines = [ln for ln in plan.split("\n") if ln.strip()]
    all_done = step_idx >= len(lines) or step_idx >= max_steps
    has_data = len(results) > 0

    if iteration >= max_iterations:
        return {"decision": "synthesize", "error": "Max iterations reached"}

    if all_done and has_data:
        return {"decision": "synthesize"}
    if all_done and not has_data:
        next_tier = constraint_tier + 1
        if next_tier >= 4:
            return {"decision": "synthesize", "error": "No results found after relaxing all constraints"}
        return {"decision": "plan", "constraint_tier": next_tier, "error": f"No results — retrying with relaxed constraints (tier {next_tier})"}

    return {"decision": "execute"}
