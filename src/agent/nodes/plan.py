from typing import Any

from langgraph.types import RunnableConfig

from src.agent.nodes.intent import _relax_intent


TIER_COUNT_MAP = {0: 8, 1: 10, 2: 12, 3: 15}
TIER_SCRAPE_MAP = {0: 3, 1: 4, 2: 5, 3: 6}


def _build_search_query(query: str, intent: dict[str, Any], tier: int = 0) -> str:
    """Build a targeted search query from the user's query and analyzed intent."""
    parts = [query.strip().rstrip(".!")]

    if tier > 0:
        intent = _relax_intent(intent, tier)

    prop_type = intent.get("property_type")
    location = intent.get("location")

    if prop_type and prop_type.lower() not in query.lower():
        parts.insert(0, prop_type)

    if location and location.lower() not in query.lower():
        parts.append(location)

    if tier < 2:
        parts.append("magicbricks 99acres")

    return " ".join(parts)


def _intent_specificity(intent: dict[str, Any]) -> int:
    count = 0
    if intent.get("location"):
        count += 1
    if intent.get("property_type"):
        count += 1
    if intent.get("budget_max") is not None or intent.get("budget_min") is not None:
        count += 1
    if intent.get("bedrooms") is not None:
        count += 1
    return count


async def plan_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state["query"]
    intent = state.get("intent", {})
    iteration = state.get("iteration", 0)
    constraint_tier = state.get("constraint_tier", 0)

    if constraint_tier == 0:
        spec = _intent_specificity(intent)
        if spec >= 4:
            search_count, scrape_count = 5, 2
        elif spec >= 2:
            search_count, scrape_count = 8, 3
        else:
            search_count, scrape_count = 15, 5
    else:
        search_count = TIER_COUNT_MAP.get(constraint_tier, 10)
        scrape_count = TIER_SCRAPE_MAP.get(constraint_tier, 4)

    search_query = _build_search_query(query, intent, constraint_tier)

    lines = [f"1. search_web(query=\"{search_query}\", count={search_count})"]
    for i in range(scrape_count):
        if i == 0:
            lines.append(f"{i + 2}. scrape_url(url=\"$result_url_1\")")
        else:
            lines.append(f"{i + 2}. scrape_url(url=\"$result_url_1_{i + 1}\")")
    for i in range(scrape_count):
        idx = i + 2 + scrape_count
        if i == 0:
            lines.append(f"{idx}. extract_property(markdown=\"$markdown_2\", source_url=\"$result_url_1\")")
        else:
            url_var = f"$result_url_1_{i + 1}"
            md_var = f"$markdown_{i + 2}"
            lines.append(f"{idx}. extract_property(markdown=\"{md_var}\", source_url=\"{url_var}\")")

    plan_text = "\n".join(lines)

    return {
        "plan": plan_text.strip(),
        "step_index": 0,
        "iteration": iteration + 1,
    }
