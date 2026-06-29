import re
from typing import Any

from langgraph.types import RunnableConfig


def _coerce(value: str) -> Any:
    stripped = value.strip().strip('"').strip("'")
    if stripped.isdigit():
        return int(stripped)
    try:
        return float(stripped)
    except ValueError:
        pass
    if stripped.lower() in ("true", "false"):
        return stripped.lower() == "true"
    return stripped


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
    step_vars = dict(state.get("step_vars", {}))

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
        if isinstance(v, str) and v.startswith("$"):
            var_name = v[1:]
            resolved_args[k] = step_vars.get(var_name, ctx.get(var_name, v))
        else:
            resolved_args[k] = _coerce(v) if isinstance(v, str) else v

    try:
        result = await tool.run(**resolved_args)
    except Exception as e:
        return {"step_index": step_idx + 1, "error": f"{tool_name} failed: {e}"}

    step_num = step_idx + 1
    if tool_name == "search_web":
        if isinstance(result, list):
            step_vars[f"result_url_{step_num}"] = result[0] if result else ""
            step_vars[f"url_{step_num}"] = result[0] if result else ""
            for i, url in enumerate(result):
                step_vars[f"result_url_{step_num}_{i+1}"] = url
    elif tool_name == "scrape_url":
        if isinstance(result, str):
            step_vars[f"markdown_{step_num}"] = result
    elif tool_name == "extract_property":
        if isinstance(result, dict):
            results.append(result)
        return {"step_index": step_idx + 1, "results": results, "step_vars": step_vars}

    if isinstance(result, list):
        results.extend(result)
    elif isinstance(result, dict):
        results.append(result)
    elif isinstance(result, str):
        results.append({"content": result, "source": tool_name})

    return {"step_index": step_idx + 1, "results": results, "step_vars": step_vars}
