from typing import Any

import httpx

from src.common.errors import NonRetryableError, ServiceError
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

FIRECRAWL_BASE_URL = "https://api.firecrawl.com/v1/scrape"
RETRYABLE_STATUSES = {429, 503}


class FirecrawlClient:
    def __init__(
        self,
        api_key: str,
        bulkhead: Bulkhead | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 30.0,
        retry_max: int = 3,
    ):
        self._api_key = api_key
        self._timeout = timeout
        self._retry_max = retry_max
        self._bulkhead = bulkhead or Bulkhead("firecrawl", max_concurrent=2)
        self._circuit_breaker = circuit_breaker or CircuitBreaker("firecrawl")

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                FIRECRAWL_BASE_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json={"url": url, "formats": ["markdown"]},
            )
            if response.status_code in RETRYABLE_STATUSES:
                response.raise_for_status()
            if response.status_code in (401, 403):
                raise NonRetryableError("firecrawl", "Invalid API key")
            if response.status_code != 200:
                raise ServiceError("firecrawl", f"HTTP {response.status_code}: {response.text}")
            data: dict[str, Any] = response.json()
            return data.get("data", {}).get("markdown", "")
