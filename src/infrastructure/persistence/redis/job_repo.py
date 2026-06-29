import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from src.domain.models.job import CrawlJob, JobStatus


class JobRepository:
    def __init__(self, redis: Redis, ttl: int = 86400):
        self._redis = redis
        self._ttl = ttl

    async def create(self, job: CrawlJob) -> None:
        key = self._key(job.search_id)
        await self._redis.setex(key, self._ttl, job.model_dump_json())

    async def update(self, search_id: str, **updates: Any) -> CrawlJob | None:
        key = self._key(search_id)
        raw = await self._redis.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        for k, v in updates.items():
            if k == "status":
                data["status"] = JobStatus(v).value
            else:
                data[k] = v
        if updates.get("status") == JobStatus.COMPLETE or updates.get("status") == JobStatus.ERROR:
            data["completed_at"] = datetime.now(timezone.utc).isoformat()
        data["created_at"] = data.get("created_at", datetime.now(timezone.utc).isoformat())
        await self._redis.setex(key, self._ttl, json.dumps(data))
        return CrawlJob(**data)

    async def get(self, search_id: str) -> CrawlJob | None:
        raw = await self._redis.get(self._key(search_id))
        if not raw:
            return None
        return CrawlJob(**json.loads(raw))

    @staticmethod
    def _key(search_id: str) -> str:
        return f"job:{search_id}"
