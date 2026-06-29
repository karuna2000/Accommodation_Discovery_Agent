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

    async def run(self, query: str, count: int = 10) -> list[str]:
        client = self._deps.brave_client
        if client:
            return await client.search(query, count=count)

        return [
            f"https://example.com/listings/apartment-{i}-near-{query.lower().replace(' ', '-')}"
            for i in range(count)
        ]
