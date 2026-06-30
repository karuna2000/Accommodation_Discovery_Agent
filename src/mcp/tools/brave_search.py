from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


@tool
class BraveSearchTool(BaseTool):
    name = "search_web"
    description = "Search the web for accommodation listings. Returns a list of relevant URLs."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query for finding listings",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (max 15)",
                "default": 10,
            },
        },
        "required": ["query"],
    }

    async def run(self, query: str, count: int = 10) -> list[dict[str, str]]:
        searxng = self._deps.searxng_client
        if searxng:
            try:
                return await searxng.search(query, count=count)
            except Exception:
                pass

        brave = self._deps.brave_client
        if brave:
            urls = await brave.search(query, count=count)
            return [{"url": u, "title": "", "snippet": "", "engine": "brave", "domain_trust_score": 0, "page_type": "unknown"} for u in urls]

        return [
            {
                "url": f"https://example.com/listings/apartment-{i}-near-{query.lower().replace(' ', '-')}",
                "title": f"Apartment {i} near {query}",
                "snippet": f"Listing {i} description",
                "engine": "mock",
                "domain_trust_score": 2,
                "page_type": "listing",
            }
            for i in range(count)
        ]
