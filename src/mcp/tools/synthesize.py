from typing import Any

from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


def _match_reasons(p: dict, intent: dict[str, Any] | None) -> list[str]:
    if not intent:
        return []
    reasons: list[str] = []

    budget = intent.get("budget_max")
    price = p.get("price_monthly")
    if budget is not None and price is not None and isinstance(price, (int, float)) and price <= float(budget):
        reasons.append(f"✓ Under ₹{int(budget):,} budget")

    budget_min = intent.get("budget_min")
    if budget_min is not None and price is not None and isinstance(price, (int, float)) and price >= float(budget_min):
        reasons.append(f"✓ Above ₹{int(budget_min):,} minimum")

    bedrooms = intent.get("bedrooms")
    prop_bed = p.get("bedrooms")
    if bedrooms is not None and prop_bed is not None and isinstance(prop_bed, (int, float)) and prop_bed >= int(bedrooms):
        reasons.append(f"✓ {'Studio' if bedrooms == 0 else f'{int(bedrooms)}+'} bedroom(s) as requested")

    loc = intent.get("location")
    if loc:
        prop_loc = p.get("location")
        addr = ""
        if isinstance(prop_loc, dict):
            addr = prop_loc.get("address", "") or ""
        elif isinstance(prop_loc, str):
            addr = prop_loc
        if loc.lower() in addr.lower() or loc.lower() in p.get("title", "").lower():
            reasons.append(f"✓ Located in/near {loc}")

    gender = intent.get("gender_preference")
    if gender:
        tags = [t.lower() for t in p.get("tags", [])]
        if gender.lower() in tags:
            reasons.append(f"✓ {gender.title()} accommodation")

    return reasons


def _fmt_property(p: dict, intent: dict[str, Any] | None = None) -> str:
    parts = []
    title = p.get("title") or p.get("source_url", "Property")
    parts.append(f"  • {title}")

    price = p.get("price_monthly")
    if price is not None:
        parts.append(f"    Price: ₹{price:,.0f}/mo")
    else:
        parts.append("    Price: N/A")

    bedrooms = p.get("bedrooms")
    if bedrooms is not None:
        parts.append(f"    Bedrooms: {bedrooms}")
    else:
        parts.append("    Bedrooms: Not specified")

    loc = p.get("location")
    if loc and isinstance(loc, dict):
        addr = loc.get("address")
        if addr:
            parts.append(f"    Location: {addr}")
        else:
            parts.append("    Location: Not specified")
    else:
        parts.append("    Location: Not specified")

    amenities = p.get("amenities")
    if amenities and isinstance(amenities, list) and len(amenities) > 0:
        parts.append(f"    Amenities: {', '.join(amenities[:5])}")
    else:
        parts.append("    Amenities: None listed")

    deposit = p.get("deposit")
    if deposit is not None:
        parts.append(f"    Deposit: ₹{deposit:,.0f}")

    lease = p.get("lease_term")
    if lease:
        parts.append(f"    Lease: {lease}")

    furnishing = p.get("furnishing_status")
    if furnishing:
        parts.append(f"    Furnishing: {furnishing}")

    food = p.get("food_included")
    if food is True:
        parts.append("    Meals: Included")
    elif food is False:
        parts.append("    Meals: Not included")

    maintenance = p.get("maintenance")
    if maintenance is not None:
        parts.append(f"    Maintenance: ₹{maintenance:,.0f}")

    tags = p.get("tags")
    if tags:
        display_tags = [t for t in tags if not t.startswith("rating:")]
        if display_tags:
            parts.append(f"    Tags: {', '.join(display_tags[:4])}")

    if p.get("source_url"):
        parts.append(f"    Source: {p['source_url']}")

    reasons = _match_reasons(p, intent)
    if reasons:
        parts.append("    " + " | ".join(reasons))

    return "\n".join(parts)


@tool
class SynthesizeTool(BaseTool):
    name = "synthesize_answer"
    description = "Generate a conversational response from a set of crawled properties. Summarizes findings and highlights key details."
    input_schema = {
        "type": "object",
        "properties": {
            "properties": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of crawled property dictionaries",
            },
            "query": {
                "type": "string",
                "description": "The original user query for context",
            },
        },
        "required": ["properties", "query"],
    }

    async def run(self, properties: list[dict], query: str, intent: dict[str, Any] | None = None) -> str:
        bedrock = self._deps.bedrock_client
        if bedrock:
            try:
                return await bedrock.synthesize(properties, query)
            except Exception:
                pass

        if not properties:
            return f"I couldn't find any properties matching '{query}'. Try refining your search."

        valid = [p for p in properties if p.get("title") and p.get("confidence", 0) >= 0.15]
        if not valid:
            valid = properties[:5]

        lines = [f"Here are {len(valid)} properties matching '{query}':", ""]
        for p in valid:
            lines.append(_fmt_property(p, intent))
            lines.append("")

        result = "\n".join(lines).strip()
        if not result or len(result) < 20:
            return f"I searched for '{query}' but couldn't find matching properties. Try different criteria."
        return result
