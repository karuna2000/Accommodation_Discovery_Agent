import pytest

from src.mcp.registry import registry
from src.mcp.tools.base import ToolDependencies


@pytest.fixture
def deps():
    return ToolDependencies()


@pytest.fixture
def tools(deps):
    return registry.create_all(deps)


def test_all_tools_registered():
    names = registry.tool_names
    assert "search_web" in names
    assert "scrape_url" in names
    assert "extract_property" in names
    assert "search_es" in names
    assert "store_property" in names
    assert "search_cache" in names
    assert "store_cache" in names
    assert "synthesize_answer" in names


def test_all_tools_have_schemas():
    schemas = registry.get_schemas()
    assert len(schemas) == len(registry.tool_names)
    for s in schemas:
        assert s["name"]
        assert s["description"]
        assert "input_schema" in s


@pytest.mark.asyncio
async def test_brave_search_returns_urls(tools):
    tool = tools["search_web"]
    result = await tool.run(query="studio near UCLA", count=3)
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(r, dict) for r in result)
    assert all(r.get("url", "").startswith("https://") for r in result)
    assert all("title" in r for r in result)
    assert all("snippet" in r for r in result)
    assert all("engine" in r for r in result)


@pytest.mark.asyncio
async def test_scrape_url_returns_markdown(tools):
    tool = tools["scrape_url"]
    result = await tool.run(url="https://example.com/listing/1")
    assert isinstance(result, str)
    assert result.startswith("#")


@pytest.mark.asyncio
async def test_extract_property_returns_crawled_properties(tools):
    tool = tools["extract_property"]
    result = await tool.run(
        markdown="# Mock Listing\n**Price:** $1200",
        source_url="https://example.com/listing/1",
    )
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["source_url"] == "https://example.com/listing/1"


@pytest.mark.asyncio
async def test_search_es_returns_empty_list(tools):
    tool = tools["search_es"]
    result = await tool.run(query={"text": "studio", "max_price": 1000})
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_store_property_returns_true(tools):
    tool = tools["store_property"]
    result = await tool.run(
        property={
            "source_url": "https://example.com",
            "source_site": "example.com",
            "title": "Test",
        }
    )
    assert result is True


@pytest.mark.asyncio
async def test_search_cache_returns_none(tools):
    tool = tools["search_cache"]
    result = await tool.run(query="studio near UCLA")
    assert result is None


@pytest.mark.asyncio
async def test_store_cache_returns_true(tools):
    tool = tools["store_cache"]
    result = await tool.run(query="test", response="test response")
    assert result is True


@pytest.mark.asyncio
async def test_synthesize_answer_returns_string(tools):
    tool = tools["synthesize_answer"]
    result = await tool.run(
        properties=[
            {"title": "Studio 1", "price_monthly": 1200, "source_url": "https://example.com/1"},
        ],
        query="studio near UCLA",
    )
    assert isinstance(result, str)
    assert "studio" in result.lower()


class TestFmtProperty:
    def test_includes_match_reasons_with_budget(self):
        from src.mcp.tools.synthesize import _fmt_property
        prop = {"title": "Apt 1", "price_monthly": 8000, "bedrooms": 2, "source_url": "https://x.com"}
        intent = {"budget_max": 10000, "bedrooms": 2}
        text = _fmt_property(prop, intent)
        assert "✓ Under" in text
        assert "✓ " in text
        assert "bedroom" in text

    def test_no_match_reasons_without_intent(self):
        from src.mcp.tools.synthesize import _fmt_property
        prop = {"title": "Apt 1", "price_monthly": 8000, "bedrooms": 2, "source_url": "https://x.com"}
        text = _fmt_property(prop)
        assert "✓" not in text

    def test_shows_location_match(self):
        from src.mcp.tools.synthesize import _fmt_property
        prop = {"title": "Apt in Jaipur", "price_monthly": 8000, "location": {"address": "Jaipur, Rajasthan"}, "source_url": "https://x.com"}
        intent = {"location": "Jaipur"}
        text = _fmt_property(prop, intent)
        assert "Jaipur" in text
