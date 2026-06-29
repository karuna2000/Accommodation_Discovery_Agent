import re
from typing import Any

from langgraph.types import RunnableConfig


def _parse_plan_line(line: str) -> tuple[str, dict[str, str]] | None:
    match = re.match(r"\d+\.\s*(\w+)\((.*)\)", line.strip())
    if not match:
        return None
    name = match.group(1)
    args_str = match.group(2)
    args: dict[str, str] = {}
    for kv in re.findall(r"(\w+)=[\"']?([^\"',)]+)[\"']?", args_str):
        args[kv[0]] = kv[1].strip().strip('"').strip("'")
    return name, args


async def execute_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    ctx = config.get("configurable", {}).get("context", {})
    tools = ctx.get("tools", {})
    plan = state.get("plan", "")
    step_idx = state.get("step_index", 0)
    results = list(state.get("results", []))

    lines = [ln for ln in plan.split("\n") if ln.strip()]
    if step_idx >= len(lines):
        return {"step_index": step_idx + 1}

    parsed = _parse_plan_line(lines[step_idx])
    if not parsed:
        return {"step_index": step_idx + 1, "error": f"Could not parse: {lines[step_idx]}"}

    tool_name, raw_args = parsed
    tool = tools.get(tool_name)
    if not tool:
        return {"step_index": step_idx + 1, "error": f"Tool {tool_name} not found"}

    resolved_args: dict[str, Any] = {}
    for k, v in raw_args.items():
        if v.startswith("$"):
            resolved_args[k] = ctx.get(v[1:], v)
        else:
            resolved_args[k] = v

    try:
        result = await tool.run(**resolved_args)
    except Exception as e:
        return {"step_index": step_idx + 1, "error": f"{tool_name} failed: {e}"}

    if isinstance(result, list):
        results.extend(result)
    elif isinstance(result, dict):
        results.append(result)
    elif isinstance(result, str):
        results.append({"content": result, "source": tool_name})

    return {"step_index": step_idx + 1, "results": results}
