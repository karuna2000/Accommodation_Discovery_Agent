from src.domain.models.property import CrawledProperty
from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


@tool
class ExtractionTool(BaseTool):
    name = "extract_property"
    description = "Extract structured property data from raw page markdown. Returns a complete property listing."
    input_schema = {
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "The raw markdown content of the page to extract data from",
            },
            "source_url": {
                "type": "string",
                "description": "The original URL of the page",
            },
        },
        "required": ["markdown", "source_url"],
    }

    async def run(self, markdown: str, source_url: str) -> CrawledProperty:
        bedrock = self._deps.bedrock_client
        if bedrock:
            return await bedrock.extract_property(markdown, source_url)

        return CrawledProperty(
            source_url=source_url,
            source_site="example.com",
            title="Mock Studio Apartment",
            description="A mock property for testing",
            price_monthly=1200.0,
            bedrooms=1,
            bathrooms=1,
            tags=["quiet", "furnished"],
            confidence=0.6,
        )
