from redis.asyncio import Redis


class IdempotencyRepository:
    def __init__(self, redis: Redis, default_ttl: int = 86400):
        self._redis = redis
        self._ttl = default_ttl

    async def try_acquire(self, key: str) -> bool:
        redis_key = self._key(key)
        setnx = await self._redis.setnx(redis_key, "in_progress")
        if setnx:
            await self._redis.expire(redis_key, self._ttl)
            return True
        return False

    async def complete(self, key: str, response_hash: str) -> None:
        await self._redis.setex(self._key(key), self._ttl, f"completed:{response_hash}")

    async def get_status(self, key: str) -> str | None:
        value = await self._redis.get(self._key(key))
        return value

    async def is_in_progress(self, key: str) -> bool:
        value = await self.get_status(key)
        return value == "in_progress"

    @staticmethod
    def _key(key: str) -> str:
        return f"idem:{key}"
