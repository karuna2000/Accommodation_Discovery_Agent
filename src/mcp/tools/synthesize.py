from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


def _fmt_property(p: dict) -> str:
    parts = []
    title = p.get("title") or p.get("source_url", "Property")
    parts.append(f"  • {title}")
    if p.get("price_monthly"):
        parts.append(f"    Price: ₹{p['price_monthly']:,.0f}/mo")
    if p.get("bedrooms") is not None:
        parts.append(f"    Bedrooms: {p['bedrooms']}")
    if p.get("location") and isinstance(p["location"], dict):
        addr = p["location"].get("address")
        if addr:
            parts.append(f"    Location: {addr}")
    if p.get("amenities"):
        amens = p["amenities"]
        if isinstance(amens, list) and len(amens) > 0:
            parts.append(f"    Amenities: {', '.join(amens[:5])}")
    if p.get("tags"):
        tags = [t for t in p["tags"] if not t.startswith("rating:")]
        if tags:
            parts.append(f"    Tags: {', '.join(tags[:4])}")
    if p.get("source_url"):
        parts.append(f"    Source: {p['source_url']}")
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

    async def run(self, properties: list[dict], query: str) -> str:
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
            lines.append(_fmt_property(p))
            lines.append("")

        return "\n".join(lines).strip()
