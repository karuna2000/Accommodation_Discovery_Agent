from typing import Any

import httpx

from src.common.errors import ServiceError
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

RETRYABLE_STATUSES = {429, 503}


class SearXNGClient:
    def __init__(
        self,
        base_url: str,
        bulkhead: Bulkhead | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 15.0,
        retry_max: int = 2,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retry_max = retry_max
        self._bulkhead = bulkhead or Bulkhead("searxng", max_concurrent=3)
        self._circuit_breaker = circuit_breaker or CircuitBreaker("searxng")

    async def search(self, query: str, count: int = 10) -> list[str]:
        return await self._bulkhead.execute(
            self._circuit_breaker.call,
            self._search,
            query,
            count,
        )

    async def _search(self, query: str, count: int) -> list[str]:
        return await retry_with_backoff(
            self._execute_request,
            query,
            count,
            max_retries=self._retry_max,
        )

    async def _execute_request(self, query: str, count: int) -> list[str]:
        return await with_timeout(
            self._do_request,
            query,
            count,
            timeout=self._timeout,
        )

    async def _do_request(self, query: str, count: int) -> list[str]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "en",
                    "categories": "general",
                    "pageno": 1,
                },
            )
            if response.status_code in RETRYABLE_STATUSES:
                response.raise_for_status()
            if response.status_code != 200:
                raise ServiceError("searxng", f"HTTP {response.status_code}: {response.text}")
            data: dict[str, Any] = response.json()
            return self._extract_urls(data, count)

    def _extract_urls(self, data: dict[str, Any], count: int) -> list[str]:
        urls: list[str] = []
        for result in data.get("results", []):
            url = result.get("url")
            if url:
                urls.append(url)
                if len(urls) >= count:
                    break
        return urls
