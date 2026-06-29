from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


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
            return await bedrock.synthesize(properties, query)

        count = len(properties)
        return (
            f"I found {count} properties matching '{query}'. "
            f"Here's a summary of the best options available."
        )
