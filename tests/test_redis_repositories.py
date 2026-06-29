import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.models.job import CrawlJob, JobStatus
from src.infrastructure.persistence.redis.cache import CacheRepository
from src.infrastructure.persistence.redis.idempotency import IdempotencyRepository
from src.infrastructure.persistence.redis.job_repo import JobRepository


@pytest.fixture
def mock_redis():
    r = MagicMock(spec_set=["get", "setex", "setnx", "expire", "scan_iter"])
    r.get = AsyncMock()
    r.setex = AsyncMock()
    r.setnx = AsyncMock(return_value=True)
    r.expire = AsyncMock()
    r.scan_iter = AsyncMock()
    return r


class TestJobRepository:
    async def test_create_stores_job(self, mock_redis):
        repo = JobRepository(mock_redis)
        job = CrawlJob(search_id="s-1", query="studio near UCLA")

        await repo.create(job)

        mock_redis.setex.assert_awaited_once()
        key = mock_redis.setex.call_args[0][0]
        assert key == "job:s-1"

    async def test_get_returns_job(self, mock_redis):
        job_data = CrawlJob(
            search_id="s-1", query="test", status=JobStatus.PLANNING
        ).model_dump_json()
        mock_redis.get.return_value = job_data

        repo = JobRepository(mock_redis)
        job = await repo.get("s-1")

        assert job is not None
        assert job.search_id == "s-1"
        assert job.status == JobStatus.PLANNING

    async def test_get_returns_none_if_missing(self, mock_redis):
        mock_redis.get.return_value = None

        repo = JobRepository(mock_redis)
        job = await repo.get("s-missing")

        assert job is None

    async def test_update_modifies_status(self, mock_redis):
        original = CrawlJob(search_id="s-1", query="test").model_dump_json()
        mock_redis.get.return_value = original

        repo = JobRepository(mock_redis)
        updated = await repo.update("s-1", status=JobStatus.COMPLETE)

        assert updated is not None
        assert updated.status == JobStatus.COMPLETE
        assert updated.completed_at is not None


class TestCacheRepository:
    async def test_store_sets_redis_key(self, mock_redis):
        repo = CacheRepository(mock_redis)
        await repo.store(query="test query", embedding=[0.1, 0.2], response="answer", ttl=3600)

        mock_redis.setex.assert_awaited_once()
        key = mock_redis.setex.call_args[0][0]
        assert key.startswith("cache:")

    async def test_get_similar_returns_exact_match(self, mock_redis):
        entry = {
            "query": "studio near UCLA",
            "response": "Here are some studios...",
            "embedding": [],
            "created_at": "2026-06-30T00:00:00+00:00",
        }
        mock_redis.get.return_value = json.dumps(entry)

        repo = CacheRepository(mock_redis)
        result = await repo.get_similar("studio near UCLA")

        assert result is not None
        assert result["response"] == "Here are some studios..."

    async def test_get_similar_returns_none_on_miss(self, mock_redis):
        mock_redis.get.return_value = None
        mock_redis.scan_iter.__aiter__.return_value = iter([])

        repo = CacheRepository(mock_redis)
        result = await repo.get_similar("nothing cached")

        assert result is None


class TestIdempotencyRepository:
    async def test_try_acquire_returns_true_first_time(self, mock_redis):
        repo = IdempotencyRepository(mock_redis)
        result = await repo.try_acquire("req-1")

        assert result is True

    async def test_try_acquire_returns_false_if_in_progress(self, mock_redis):
        mock_redis.setnx.return_value = False

        repo = IdempotencyRepository(mock_redis)
        result = await repo.try_acquire("req-1")

        assert result is False

    async def test_complete_stores_hash(self, mock_redis):
        repo = IdempotencyRepository(mock_redis)
        await repo.complete("req-1", "hash123")

        mock_redis.setex.assert_awaited_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "idem:req-1"
        assert "completed:hash123" in args

    async def test_is_in_progress_checks_status(self, mock_redis):
        mock_redis.get.return_value = "in_progress"

        repo = IdempotencyRepository(mock_redis)
        result = await repo.is_in_progress("req-1")

        assert result is True
