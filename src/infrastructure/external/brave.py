from typing import Any

import httpx

from src.common.errors import NonRetryableError, ServiceError
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

BRAVE_BASE_URL = "https://api.search.brave.com/res/v1/web/search"
RETRYABLE_STATUSES = {429, 503}


class BraveClient:
    def __init__(
        self,
        api_key: str,
        bulkhead: Bulkhead | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 10.0,
        retry_max: int = 3,
    ):
        self._api_key = api_key
        self._timeout = timeout
        self._retry_max = retry_max
        self._bulkhead = bulkhead or Bulkhead("brave", max_concurrent=2)
        self._circuit_breaker = circuit_breaker or CircuitBreaker("brave")

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
                BRAVE_BASE_URL,
                headers={"Accept": "application/json", "X-Subscription-Token": self._api_key},
                params={"q": query, "count": count},
            )
            if response.status_code in RETRYABLE_STATUSES:
                response.raise_for_status()
            if response.status_code == 401:
                raise NonRetryableError("brave", "Invalid API key")
            if response.status_code == 402:
                raise NonRetryableError("brave", "API rate limit exceeded (paywall)")
            if response.status_code != 200:
                raise ServiceError("brave", f"HTTP {response.status_code}: {response.text}")
            data: dict[str, Any] = response.json()
            return self._extract_urls(data)

    def _extract_urls(self, data: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        for result in data.get("web", {}).get("results", []):
            url = result.get("url")
            if url:
                urls.append(url)
        return urls
