from typing import Any

from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


@tool
class SearchCacheTool(BaseTool):
    name = "search_cache"
    description = "Check if a similar query was already answered. Returns cached response if found (cosine similarity > 0.90)."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The user's search query to look up in cache",
            },
        },
        "required": ["query"],
    }

    async def run(self, query: str) -> Any:
        repo = self._deps.cache_repo
        if repo:
            return await repo.get_similar(query, threshold=0.90)

        return None


@tool
class StoreCacheTool(BaseTool):
    name = "store_cache"
    description = "Store a synthesized answer in the cache so similar queries can reuse it."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The original search query",
            },
            "response": {
                "type": "string",
                "description": "The synthesized answer to cache",
            },
        },
        "required": ["query", "response"],
    }

    async def run(self, query: str, response: str) -> bool:
        repo = self._deps.cache_repo
        if repo:
            await repo.store(query=query, embedding=[], response=response, ttl=86400)
            return True

        return True
