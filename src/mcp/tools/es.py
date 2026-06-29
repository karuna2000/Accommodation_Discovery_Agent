from src.domain.models.property import CrawledProperty
from src.domain.models.search import SearchQuery
from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


@tool
class SearchESTool(BaseTool):
    name = "search_es"
    description = "Search previously crawled properties in Elasticsearch using hybrid (semantic + keyword + geo) search."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "object",
                "description": "The search parameters",
                "properties": {
                    "text": {"type": "string", "description": "Natural language search text"},
                    "max_price": {"type": "number", "description": "Maximum monthly price"},
                    "min_bedrooms": {"type": "integer", "description": "Minimum bedrooms"},
                    "location_hint": {"type": "string", "description": "Area or address hint"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required tags (e.g., quiet, furnished)",
                    },
                },
            },
        },
        "required": ["query"],
    }

    async def run(self, query: dict) -> list[CrawledProperty]:
        repo = self._deps.search_repo
        if repo:
            search_query = SearchQuery(
                raw=query.get("text", ""),
                max_price=query.get("max_price"),
                min_bedrooms=query.get("min_bedrooms"),
                location_hint=query.get("location_hint"),
                tags=query.get("tags", []),
            )
            return await repo.search_hybrid(search_query, embedding=[])

        return []


@tool
class StoreESTool(BaseTool):
    name = "store_property"
    description = "Store a crawled property in Elasticsearch so it can be found by future searches."
    input_schema = {
        "type": "object",
        "properties": {
            "property": {
                "type": "object",
                "description": "The property data to store",
            },
        },
        "required": ["property"],
    }

    async def run(self, property: dict) -> bool:
        repo = self._deps.search_repo
        if repo:
            prop = CrawledProperty(**property)
            await repo.store(prop)
            return True

        return True
