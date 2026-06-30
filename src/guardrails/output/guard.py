import json
from typing import Any

from src.guardrails.output.pii import strip_pii


_TEXT_FIELDS = {"title", "description", "address", "reviews_summary", "location"}
_LIST_FIELDS = {"tags", "amenities", "images", "requirements"}

_CORE_FIELDS = {"title", "price_monthly", "bedrooms", "source_url"}
_CORE_OPTIONAL = {"location", "property_type"}
_SECONDARY_FIELDS = {"amenities", "images", "deposit", "lease_term", "furnishing_status", "reviews_summary", "house_rules", "availability_date"}


def strip_pii_from_properties(properties: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for prop in properties:
        if not isinstance(prop, dict):
            cleaned.append(prop)
            continue
        p = dict(prop)
        for key in list(p.keys()):
            val = p[key]
            if key in _TEXT_FIELDS and isinstance(val, str):
                p[key] = strip_pii(val)
            elif key == "location" and isinstance(val, dict):
                loc = dict(val)
                if isinstance(loc.get("address"), str):
                    loc["address"] = strip_pii(loc["address"])
                p[key] = loc
            elif key in _LIST_FIELDS and isinstance(val, list):
                p[key] = [strip_pii(str(item)) for item in val]
        cleaned.append(p)
    return cleaned


def _score_completeness(prop: dict) -> dict[str, Any]:
    filled = 0
    total = len(_CORE_FIELDS) + len(_CORE_OPTIONAL) + len(_SECONDARY_FIELDS)
    for field in _CORE_FIELDS:
        val = prop.get(field)
        if val is not None and (not isinstance(val, (list, str)) or len(val) > 0):
            filled += 1
    for field in _CORE_OPTIONAL:
        val = prop.get(field)
        if val is not None and (not isinstance(val, (list, str)) or len(val) > 0):
            filled += 1
    for field in _SECONDARY_FIELDS:
        val = prop.get(field)
        if val is not None and (not isinstance(val, (list, str)) or len(val) > 0):
            filled += 1
    core_filled = sum(1 for f in _CORE_FIELDS if prop.get(f) is not None and (not isinstance(prop.get(f), (list, str)) or len(prop.get(f)) > 0))
    core_total = len(_CORE_FIELDS)
    pct = (filled / total) * 100 if total > 0 else 0
    core_pct = (core_filled / core_total) * 100 if core_total > 0 else 0
    return {
        "filled": filled,
        "total": total,
        "percent": round(pct, 1),
        "core_percent": round(core_pct, 1),
        "low_confidence": core_pct < 60,
        "very_low": core_pct < 40,
    }


def _query_matches_intent(
    prop: dict, query: str, intent: dict[str, Any]
) -> bool:
    text = f"{prop.get('title', '')} {prop.get('description', '')} {prop.get('address', '')}".lower()
    query_lower = query.lower()

    max_budget = intent.get("budget_max")
    if max_budget is not None:
        price = prop.get("price_monthly")
        if price is not None and isinstance(price, (int, float)):
            if price > float(max_budget) * 1.2:
                score = prop.get("confidence", 0.2)
                if score < 0.4:
                    return False

    min_budget = intent.get("budget_min")
    if min_budget is not None:
        price = prop.get("price_monthly")
        if price is not None and isinstance(price, (int, float)):
            if price < float(min_budget) * 0.8:
                score = prop.get("confidence", 0.2)
                if score < 0.4:
                    return False

    bedrooms = intent.get("bedrooms")
    if bedrooms is not None:
        prop_bed = prop.get("bedrooms")
        if prop_bed is not None and isinstance(prop_bed, (int, float)):
            if prop_bed < int(bedrooms):
                score = prop.get("confidence", 0.2)
                if score < 0.4:
                    return False

    gender = intent.get("gender_preference")
    if gender:
        safe_tags = [t.lower() for t in prop.get("tags", [])]
        if "boys" in safe_tags and gender.lower() in ("girls", "ladies", "female"):
            return False
        if "girls" in safe_tags and gender.lower() in ("boys", "gents", "male"):
            return False

    loc = intent.get("location")
    if loc:
        loc_lower = loc.lower()
        if loc_lower not in text and loc_lower not in query_lower:
            score = prop.get("confidence", 0.2)
            if score < 0.25:
                return False

    return True


def _filter_vague_properties(
    properties: list[dict], query: str, intent: dict[str, Any]
) -> tuple[list[dict], list[str]]:
    filtered: list[dict] = []
    issues: list[str] = []
    for prop in properties:
        if not isinstance(prop, dict):
            filtered.append(prop)
            continue
        pid = prop.get("property_id", prop.get("title", "unknown"))
        if _query_matches_intent(prop, query, intent):
            filtered.append(prop)
        else:
            issues.append(f"Removed property '{pid}' — does not match query constraints")
    return filtered, issues


async def validate_results(
    properties: list[dict],
    query: str,
    intent: dict[str, Any] | None = None,
    bedrock_client: Any | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    intent = intent or {}
    text_fields_initial = _count_text_chars(properties)

    pii_stripped = strip_pii_from_properties(properties)

    if bedrock_client:
        try:
            return await _llm_validate(pii_stripped, query, intent, bedrock_client)
        except Exception:
            pass

    return _fallback_validate(pii_stripped, query, intent, text_fields_initial)


async def _llm_validate(
    properties: list[dict],
    query: str,
    intent: dict[str, Any],
    bedrock: Any,
) -> tuple[list[dict], dict[str, Any]]:
    prompt = (
        "You are a quality assurance validator for accommodation search results.\n\n"
        f"User query: {query}\n"
        f"User requirements: {json.dumps(intent)}\n\n"
        "Validate these extracted property results:\n"
        f"{json.dumps(properties, indent=2, default=str)}\n\n"
        "For each property:\n"
        "1. Strip any PII (phone numbers, emails, SSNs, credit card numbers) from ALL text fields\n"
        "2. Check if the property is relevant to the user's query (budget, bedrooms, location, property type, gender)\n"
        "3. Remove properties that clearly don't match\n\n"
        "Return ONLY valid JSON with:\n"
        "- results: list of cleaned property dicts (PII removed, irrelevant ones excluded)\n"
        "- issues: list of strings describing what was removed/changed\n"
        "- properties_filtered: int (count of properties removed)\n"
        "- passed: bool (true if all remaining properties seem valid)\n\n"
        "No explanation, no markdown, no code blocks."
    )

    raw = await bedrock.invoke_with_fallback(prompt, max_tokens=4096)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0] if "```" in raw else raw
    raw = raw.strip()
    result = json.loads(raw)

    cleaned = result.get("results", properties)
    issues = result.get("issues", [])
    passed = result.get("passed", len(issues) == 0)

    cleaned = strip_pii_from_properties(cleaned)

    report: dict[str, Any] = {
        "passed": passed,
        "issues": issues,
        "properties_filtered": result.get("properties_filtered", 0),
        "pii_stripped": True,
        "method": "llm",
    }
    return cleaned, report


def _flag_low_confidence(properties: list[dict]) -> tuple[list[dict], list[str]]:
    kept: list[dict] = []
    issues: list[str] = []
    for prop in properties:
        if not isinstance(prop, dict):
            kept.append(prop)
            continue
        score = _score_completeness(prop)
        prop = dict(prop)
        prop["completeness"] = score
        if score["very_low"]:
            pid = prop.get("property_id", prop.get("title", "unknown"))
            issues.append(f"Excluded property '{pid}' — very low completeness ({score['core_percent']}% core fields)")
            continue
        kept.append(prop)
    return kept, issues


def _fallback_validate(
    properties: list[dict],
    query: str,
    intent: dict[str, Any],
    text_chars_before: int,
) -> tuple[list[dict], dict[str, Any]]:
    filtered, issues = _filter_vague_properties(properties, query, intent)
    text_chars_after = _count_text_chars(filtered)
    pii_found = text_chars_before > text_chars_after

    scored, completeness_issues = _flag_low_confidence(filtered)
    issues.extend(completeness_issues)

    report: dict[str, Any] = {
        "passed": len(issues) == 0,
        "issues": issues,
        "properties_filtered": (len(properties) - len(scored)),
        "pii_stripped": pii_found,
        "method": "fallback",
    }
    return scored, report


def _count_text_chars(properties: list[dict]) -> int:
    total = 0
    for p in properties:
        if not isinstance(p, dict):
            continue
        for key in _TEXT_FIELDS:
            val = p.get(key)
            if isinstance(val, str):
                total += len(val)
        for key in _LIST_FIELDS:
            vals = p.get(key)
            if isinstance(vals, list):
                for item in vals:
                    if isinstance(item, str):
                        total += len(item)
    return total
