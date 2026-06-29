from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.models.property import CrawledProperty, Location
from src.domain.models.search import SearchQuery
from src.infrastructure.persistence.elasticsearch.repository import (
    CrawledPropertyESRepository,
    today_index,
)


from elasticsearch import NotFoundError


@pytest.fixture
def mock_es():
    es = MagicMock(spec_set=["indices", "index", "search"])
    es.indices = MagicMock()
    es.indices.exists = AsyncMock()
    es.indices.create = AsyncMock()
    es.indices.get = AsyncMock()
    es.indices.delete = AsyncMock()
    es.index = AsyncMock()
    es.search = AsyncMock()
    return es


@pytest.fixture
def repo(mock_es):
    return CrawledPropertyESRepository(mock_es, "test-props")


class TestTodayIndex:
    def test_returns_date_formatted_index(self):
        result = today_index("props")
        assert result.startswith("props-")


class TestStore:
    async def test_creates_index_on_first_store(self, repo, mock_es):
        mock_es.indices.exists.return_value = False
        prop = CrawledProperty(
            source_url="https://example.com/apt",
            source_site="example.com",
            title="Test Apt",
        )
        await repo.store(prop)

        mock_es.indices.create.assert_awaited_once()
        mock_es.index.assert_awaited_once()

    async def test_skips_index_creation_if_exists(self, repo, mock_es):
        mock_es.indices.exists.return_value = True
        prop = CrawledProperty(
            source_url="https://example.com/apt",
            source_site="example.com",
            title="Test Apt",
        )
        await repo.store(prop)

        mock_es.indices.create.assert_not_called()
        mock_es.index.assert_awaited_once()

    async def test_stores_with_geo_location(self, repo, mock_es):
        mock_es.indices.exists.return_value = True
        prop = CrawledProperty(
            source_url="https://example.com/apt",
            source_site="example.com",
            title="Test Apt",
            location=Location(lat=34.05, lng=-118.25, address="Los Angeles"),
        )
        await repo.store(prop)

        call_kwargs = mock_es.index.call_args[1]
        body = call_kwargs["body"]
        assert body["location"] == {"lat": 34.05, "lon": -118.25}
        assert body["address"] == "Los Angeles"


class TestSearch:
    async def test_returns_empty_on_missing_index(self, repo, mock_es):
        mock_es.search.side_effect = NotFoundError("index not found", {}, {})
        mock_es.indices.exists.return_value = True

        q = SearchQuery(raw="test")
        results = await repo.search_hybrid(q)

        assert results == []

    async def test_returns_properties_from_hits(self, repo, mock_es):
        mock_es.indices.exists.return_value = True
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "abc-123",
                        "_source": {
                            "property_id": "abc-123",
                            "source_url": "https://example.com/apt",
                            "source_site": "example.com",
                            "title": "Found Apt",
                            "crawled_at": "2026-06-30T00:00:00Z",
                        },
                    }
                ]
            }
        }

        q = SearchQuery(raw="found")
        results = await repo.search_hybrid(q)

        assert len(results) == 1
        assert results[0].title == "Found Apt"
        assert results[0].source_url == "https://example.com/apt"

    async def test_builds_filters_from_query(self, repo, mock_es):
        mock_es.indices.exists.return_value = True
        mock_es.search.return_value = {"hits": {"hits": []}}

        q = SearchQuery(raw="studio", max_price=1500.0, min_bedrooms=1, tags=["furnished"])
        await repo.search_hybrid(q)

        call_kwargs = mock_es.search.call_args[1]
        body = call_kwargs["body"]
        filters = body["query"]["bool"]["filter"]
        assert any("price_monthly" in str(f) for f in filters)
        assert any("bedrooms" in str(f) for f in filters)
        assert any("tags" in str(f) for f in filters)


class TestDeleteOldIndices:
    async def test_deletes_expired_indices(self, repo, mock_es):
        mock_es.indices.get.return_value = {
            "props-2026.01.01": {},
            "props-2026.06.30": {},
        }
        mock_es.indices.delete = AsyncMock()

        deleted = await repo.delete_old_indices(retention_days=2)

        assert deleted == 1
        mock_es.indices.delete.assert_awaited_once_with(index="props-2026.01.01")

    async def test_handles_no_indices(self, repo, mock_es):
        mock_es.indices.get.side_effect = NotFoundError("index not found", {}, {})

        deleted = await repo.delete_old_indices()

        assert deleted == 0
