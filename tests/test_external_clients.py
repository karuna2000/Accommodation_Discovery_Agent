from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.external.brave import BraveClient
from src.infrastructure.external.firecrawl import FirecrawlClient


class TestBraveClient:
    @patch("httpx.AsyncClient.get")
    async def test_search_returns_urls(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"url": "https://example.com/apt1"},
                    {"url": "https://example.com/apt2"},
                ]
            }
        }
        mock_get.return_value = mock_response

        client = BraveClient(api_key="fake-key", timeout=5, retry_max=0)
        urls = await client.search("studio near UCLA")

        assert urls == ["https://example.com/apt1", "https://example.com/apt2"]

    @patch("httpx.AsyncClient.get")
    async def test_handles_empty_results(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"web": {"results": []}}
        mock_get.return_value = mock_response

        client = BraveClient(api_key="fake-key", timeout=5, retry_max=0)
        urls = await client.search("zzzzzznothing")

        assert urls == []

    @patch("httpx.AsyncClient.get")
    async def test_raises_on_401(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = BraveClient(api_key="bad-key", timeout=5, retry_max=0)
        from src.common.errors import NonRetryableError

        with pytest.raises(NonRetryableError, match="Invalid API key"):
            await client.search("test")


class TestFirecrawlClient:
    @patch("httpx.AsyncClient.post")
    async def test_scrape_returns_markdown(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"markdown": "# Listing\n\nGreat place"}
        }
        mock_post.return_value = mock_response

        client = FirecrawlClient(api_key="fake-key", timeout=5, retry_max=0)
        content = await client.scrape("https://example.com/apt")

        assert content == "# Listing\n\nGreat place"

    @patch("httpx.AsyncClient.post")
    async def test_handles_empty_content(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"markdown": ""}}
        mock_post.return_value = mock_response

        client = FirecrawlClient(api_key="fake-key", timeout=5, retry_max=0)
        content = await client.scrape("https://example.com/apt")

        assert content == ""

    @patch("httpx.AsyncClient.post")
    async def test_raises_on_403(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_post.return_value = mock_response

        client = FirecrawlClient(api_key="bad-key", timeout=5, retry_max=0)
        from src.common.errors import NonRetryableError

        with pytest.raises(NonRetryableError, match="Invalid API key"):
            await client.scrape("https://example.com/apt")
