from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


@tool
class FirecrawlTool(BaseTool):
    name = "scrape_url"
    description = "Scrape a URL and return the page content as clean markdown. Handles JavaScript-rendered pages."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to scrape",
            },
        },
        "required": ["url"],
    }

    async def run(self, url: str) -> str:
        client = self._deps.firecrawl_client
        if client:
            return await client.scrape(url)

        return f"""# Mock Listing from {url}

**Price:** $1,200/month
**Location:** 123 University Ave, Los Angeles, CA
**Bedrooms:** 1
**Bathrooms:** 1

Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a mock listing description for testing purposes.

**Amenities:** WiFi, Laundry, Parking, Air Conditioning
**Reviews:** Great location, quiet neighborhood, responsive landlord.
"""
