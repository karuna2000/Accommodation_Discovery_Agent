import json
import math
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from redis.asyncio import Redis


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


class CacheRepository:
    def __init__(
        self,
        redis: Redis,
        bedrock_client: Any | None = None,
        default_ttl: int = 86400,
        similarity_threshold: float = 0.90,
    ):
        self._redis = redis
        self._bedrock = bedrock_client
        self._default_ttl = default_ttl
        self._threshold = similarity_threshold

    async def store(
        self,
        query: str,
        embedding: list[float] | None,
        response: str,
        ttl: int | None = None,
    ) -> None:
        if not embedding and self._bedrock:
            try:
                embedding = await self._bedrock.generate_embedding(query)
            except Exception:
                embedding = []
        if not embedding:
            embedding = []

        key = self._key(query)
        value = json.dumps({
            "query": query,
            "response": response,
            "embedding": embedding,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        ttl = ttl or self._default_ttl
        await self._redis.setex(key, ttl, value)

    async def get_similar(
        self,
        query: str,
        threshold: float | None = None,
        embedding: list[float] | None = None,
    ) -> dict | None:
        threshold = threshold or self._threshold

        if not embedding and self._bedrock:
            try:
                embedding = await self._bedrock.generate_embedding(query)
            except Exception:
                embedding = []

        exact_key = self._key(query)
        exact_raw = await self._redis.get(exact_key)
        if exact_raw:
            entry = json.loads(exact_raw)
            return entry

        if embedding:
            best: dict | None = None
            best_score = 0.0
            async for key in self._redis.scan_iter(match="cache:*"):
                if key == exact_key:
                    continue
                raw = await self._redis.get(key)
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                stored_emb = entry.get("embedding", [])
                if stored_emb:
                    score = _cosine_similarity(embedding, stored_emb)
                    if score > best_score:
                        best_score = score
                        best = entry
            if best and best_score >= threshold:
                return best

        return None

    @staticmethod
    def _key(query: str) -> str:
        return f"cache:{sha256(query.encode()).hexdigest()}"
