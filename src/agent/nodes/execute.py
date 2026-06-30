import re
from typing import Any
from urllib.parse import urlparse

from langgraph.types import RunnableConfig

_ACCOMMODATION_DOMAINS: set[str] = {
    "magicbricks.com",
    "99acres.com",
    "nobroker.in",
    "nestaway.com",
    "housing.com",
    "commonfloor.com",
    "makaan.com",
    "sulekha.com",
    "quikr.com",
    "olx.in",
    "propertywala.com",
    "squareyards.com",
}

_ACCOMMODATION_KWS = {
    "rent", "pg", "hostel", "apartment", "flat", "room",
    "accommodation", "studio", "bhk", "property", "house",
    "for rent", "pg in", "listing", "property",
}


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


def _is_url_relevant(url: str, title: str, snippet: str, intent: dict[str, Any]) -> bool:
    domain = urlparse(url).netloc.lower().removeprefix("www.")

    if domain in _ACCOMMODATION_DOMAINS:
        return True

    combined = (title + " " + snippet).lower()
    if any(kw in combined for kw in _ACCOMMODATION_KWS):
        return True

    prop_type = intent.get("property_type")
    if prop_type and prop_type.lower() in combined:
        return True

    loc = intent.get("location")
    if loc and loc.lower() in combined:
        return True

    # URL has listing-like path
    if re.search(r"/(?:property-detail|detail/|listing/|pg/|rent/)", url, re.IGNORECASE):
        return True

    return False


_QUERY_BUDGET_RE = re.compile(
    r"(?:under|max(?:imum)?|budget|within|below|upto|up to)\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_QUERY_BUDGET_MIN_RE = re.compile(
    r"(?:above|min(?:imum)?|at\s*least|starting\s*(?:from|at)|from)\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_QUERY_BHK_RE = re.compile(r"(\d+)\s*B[Hh][Kk]", re.IGNORECASE)
_QUERY_BOYS_RE = re.compile(r"\b(boys?|gents?|male)\b", re.IGNORECASE)
_QUERY_GIRLS_RE = re.compile(r"\b(girls?|ladies?|female|women|womens)\b", re.IGNORECASE)
_QUERY_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)
_QUERY_LOCATION_RE = re.compile(
    r"(?:in|near|at|around)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
)


def _filter_properties_by_query(properties: list[dict], query: str) -> list[dict]:
    """Shortlist extracted properties to only keep ones matching the user's query constraints."""
    if not properties:
        return []
    if not query:
        return properties

    max_price: float | None = None
    for m in _QUERY_BUDGET_RE.finditer(query):
        val = float(m.group(1).replace(",", ""))
        if max_price is None or val < max_price:
            max_price = val

    min_price: float | None = None
    for m in _QUERY_BUDGET_MIN_RE.finditer(query):
        val = float(m.group(1).replace(",", ""))
        if min_price is None or val < min_price:
            min_price = val
    range_match = re.search(r"(\d[\d,.]*)\s*(?:-|to)\s*(\d[\d,.]*)", query)
    if range_match:
        lo = float(range_match.group(1).replace(",", ""))
        hi = float(range_match.group(2).replace(",", ""))
        min_price = min(lo, hi) if min_price is None else min(min_price, lo)

    min_bedrooms: int | None = None
    bhk_m = _QUERY_BHK_RE.search(query)
    if bhk_m:
        min_bedrooms = int(bhk_m.group(1))
    if _QUERY_STUDIO_RE.search(query):
        min_bedrooms = 0

    gender_filter: str | None = None
    if _QUERY_BOYS_RE.search(query):
        gender_filter = "boys"
    elif _QUERY_GIRLS_RE.search(query):
        gender_filter = "girls"

    location_kws: list[str] = []
    for m in _QUERY_LOCATION_RE.finditer(query):
        place = m.group(1).strip()
        if place.lower() not in ("the", "a", "an", "for", "under", "with", "near", "around"):
            location_kws.append(place)

    matched: list[dict] = []
    for prop in properties:
        score = 0.0
        checks = 0.0

        if max_price is not None:
            checks += 1.0
            p = prop.get("price_monthly")
            if p is not None and isinstance(p, (int, float)) and p <= max_price:
                score += 1.0
            elif p is None:
                score += 0.5

        if min_price is not None:
            checks += 1.0
            p = prop.get("price_monthly")
            if p is not None and isinstance(p, (int, float)) and p >= min_price:
                score += 1.0
            elif p is None:
                score += 0.5

        if min_bedrooms is not None:
            checks += 1.0
            b = prop.get("bedrooms")
            if b is not None and isinstance(b, int) and b >= min_bedrooms:
                score += 1.0
            elif b is None:
                score += 0.5

        if gender_filter:
            checks += 1.0
            tags = prop.get("tags", [])
            if isinstance(tags, list) and gender_filter in tags:
                score += 1.0
            elif not tags:
                score += 0.5

        if location_kws:
            checks += 1.0
            loc = prop.get("location", {}) or {}
            address = loc.get("address", "") if isinstance(loc, dict) else str(loc) if loc else ""
            if address and any(kw.lower() in address.lower() for kw in location_kws):
                score += 1.0
            elif not address:
                score += 0.5

        if checks == 0:
            matched.append(prop)
        elif score / checks >= 0.5:
            matched.append(prop)

    return matched


async def execute_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    ctx = config.get("configurable", {}).get("context", {})
    tools = ctx.get("tools", {})
    plan = state.get("plan", "")
    step_idx = state.get("step_index", 0)
    results = list(state.get("results", []))
    step_vars = dict(state.get("step_vars", {}))
    page_stats = list(state.get("page_stats", []))
    intent = state.get("intent", {})

    lines = [ln for ln in plan.split("\n") if ln.strip()]
    if step_idx >= len(lines):
        return {"step_index": step_idx + 1, "page_stats": page_stats}

    parsed = _parse_plan_line(lines[step_idx])
    if not parsed:
        return {"step_index": step_idx + 1, "error": f"Could not parse: {lines[step_idx]}", "page_stats": page_stats}

    tool_name, raw_args = parsed
    tool = tools.get(tool_name)
    if not tool:
        return {"step_index": step_idx + 1, "error": f"Tool {tool_name} not found", "page_stats": page_stats}

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
        return {"step_index": step_idx + 1, "error": f"{tool_name} failed: {e}", "page_stats": page_stats}

    step_num = step_idx + 1

    if tool_name == "search_web":
        if isinstance(result, list):
            base = step_vars.get(f"search_meta_{step_num}", [])
            if result and isinstance(result[0], dict):
                base.extend(result)
                step_vars[f"result_url_{step_num}"] = result[0].get("url", "")
                step_vars[f"url_{step_num}"] = result[0].get("url", "")
                for i, r in enumerate(result):
                    step_vars[f"result_url_{step_num}_{i+1}"] = r.get("url", "")
                step_vars[f"search_meta_{step_num}"] = result
            elif result and isinstance(result[0], str):
                step_vars[f"result_url_{step_num}"] = result[0]
                step_vars[f"url_{step_num}"] = result[0]
                for i, url in enumerate(result):
                    step_vars[f"result_url_{step_num}_{i+1}"] = url
        return {"step_index": step_idx + 1, "step_vars": step_vars, "page_stats": page_stats}

    if tool_name == "scrape_url":
        url = resolved_args.get("url", "")
        meta_list = step_vars.get(f"search_meta_{step_num - 1}", []) if step_num > 1 else []
        meta = next((m for m in meta_list if isinstance(m, dict) and m.get("url") == url), None)
        if meta and not _is_url_relevant(url, meta.get("title", ""), meta.get("snippet", ""), intent):
            step_vars[f"markdown_{step_num}"] = ""
            page_stats.append({"url": url, "skipped": True, "reason": "Not relevant to query"})
            return {"step_index": step_idx + 1, "step_vars": step_vars, "page_stats": page_stats}
        if isinstance(result, str):
            step_vars[f"markdown_{step_num}"] = result
        return {"step_index": step_idx + 1, "step_vars": step_vars, "page_stats": page_stats}

    if tool_name == "extract_property":
        from src.domain.models.property import CrawledProperty, Location

        props = result if isinstance(result, list) else ([result] if isinstance(result, dict) else [])
        matched = _filter_properties_by_query(props, state.get("query", ""))
        source_url = resolved_args.get("source_url", "")
        page_stats.append({
            "url": source_url,
            "properties_found": len(props),
            "properties_matched": len(matched),
        })

        search_repo = ctx.get("search_repo")
        if search_repo:
            for p in props:
                try:
                    cp = CrawledProperty(**{k: v for k, v in p.items() if k in CrawledProperty.model_fields})
                    if cp.title:
                        await search_repo.store(cp)
                except Exception:
                    pass

        results.extend(matched)
        return {"step_index": step_idx + 1, "results": results, "step_vars": step_vars, "page_stats": page_stats}

    if isinstance(result, list):
        results.extend(result)
    elif isinstance(result, dict):
        results.append(result)
    elif isinstance(result, str):
        results.append({"content": result, "source": tool_name})

    return {"step_index": step_idx + 1, "results": results, "step_vars": step_vars, "page_stats": page_stats}
