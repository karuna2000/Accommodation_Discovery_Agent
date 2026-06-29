from typing import Any

import httpx

from src.common.errors import NonRetryableError, ServiceError
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

RETRYABLE_STATUSES = {429, 503}


class Crawl4AIClient:
    def __init__(
        self,
        base_url: str,
        api_token: str = "",
        bulkhead: Bulkhead | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 60.0,
        retry_max: int = 2,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._timeout = timeout
        self._retry_max = retry_max
        self._bulkhead = bulkhead or Bulkhead("crawl4ai", max_concurrent=2)
        self._circuit_breaker = circuit_breaker or CircuitBreaker("crawl4ai")

    async def scrape(self, url: str) -> str:
        return await self._bulkhead.execute(
            self._circuit_breaker.call,
            self._scrape,
            url,
        )

    async def _scrape(self, url: str) -> str:
        return await retry_with_backoff(
            self._execute_request,
            url,
            max_retries=self._retry_max,
        )

    async def _execute_request(self, url: str) -> str:
        return await with_timeout(
            self._do_request,
            url,
            timeout=self._timeout,
        )

    async def _do_request(self, url: str) -> str:
        headers = {}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/crawl",
                headers=headers or None,
                json={"urls": [url]},
            )
            if response.status_code in RETRYABLE_STATUSES:
                response.raise_for_status()
            if response.status_code != 200:
                raise ServiceError("crawl4ai", f"HTTP {response.status_code}: {response.text}")
            data: dict[str, Any] = response.json()
            if not data.get("success"):
                raise NonRetryableError("crawl4ai", str(data.get("error", "unknown error")))
            results = data.get("results", [])
            if not results:
                return ""
            return results[0].get("markdown", {}).get("raw_markdown", "")
