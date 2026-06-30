import re
from typing import Any
from urllib.parse import urlparse

import httpx

from src.common.errors import ServiceError
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

RETRYABLE_STATUSES = {429, 503}

_ACCOMMODATION_DOMAINS: set[str] = {
    "magicbricks.com",
    "99acres.com",
    "nobroker.in",
    "nestaway.com",
    "housing.com",
    "commonfloor.com",
    "makaan.com",
    "sulekha.com",
    "quikr.com",
    "olx.in",
    "propertywala.com",
    "squareyards.com",
}

_NON_ACCOMMODATION_DOMAINS: set[str] = {
    "wikipedia.org",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "linkedin.com",
    "reddit.com",
    "amazon.in",
    "flipkart.com",
    "pinterest.com",
}

_LISTING_PATH_RE = re.compile(
    r"/(?:property-detail|detail/|listing/|view/|"
    r"property-for-rent|flat-for-rent)/",
    re.IGNORECASE,
)

_CATEGORY_PATH_RE = re.compile(
    r"/(?:properties-in|search/|category/|pppfs)",
    re.IGNORECASE,
)

_PID_RE = re.compile(r"pid\d+", re.IGNORECASE)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _score_url(url: str) -> int:
    score = 0
    domain = _domain(url)
    path = urlparse(url).path

    if domain in _ACCOMMODATION_DOMAINS:
        score += 2
    elif domain in _NON_ACCOMMODATION_DOMAINS:
        score -= 5
    else:
        score -= 1

    if _LISTING_PATH_RE.search(path):
        score += 4
    if _PID_RE.search(path):
        score += 3
    if _CATEGORY_PATH_RE.search(path):
        score -= 2
    if re.search(r"/\d{5,}", path):
        score += 2

    return score


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

    async def search(self, query: str, count: int = 10) -> list[dict[str, Any]]:
        return await self._bulkhead.execute(
            self._circuit_breaker.call,
            self._search,
            query,
            count,
        )

    async def _search(self, query: str, count: int) -> list[dict[str, Any]]:
        return await retry_with_backoff(
            self._execute_request,
            query,
            count,
            max_retries=self._retry_max,
        )

    async def _execute_request(self, query: str, count: int) -> list[dict[str, Any]]:
        return await with_timeout(
            self._do_request,
            query,
            count,
            timeout=self._timeout,
        )

    async def _do_request(self, query: str, count: int) -> list[dict[str, Any]]:
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

    def _extract_urls(self, data: dict[str, Any], count: int) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for result in data.get("results", []):
            url = result.get("url")
            if not url:
                continue
            score = _score_url(url)
            path = urlparse(url).path
            if _LISTING_PATH_RE.search(path):
                page_type = "listing"
            elif _CATEGORY_PATH_RE.search(path):
                page_type = "category"
            else:
                page_type = "unknown"
            entry: dict[str, Any] = {
                "url": url,
                "title": result.get("title", ""),
                "snippet": result.get("content", ""),
                "engine": result.get("engine", ""),
                "domain_trust_score": score,
                "page_type": page_type,
            }
            existing = seen.get(url)
            if existing is None or score > existing.get("domain_trust_score", -999):
                seen[url] = entry

        ranked = sorted(
            seen.values(),
            key=lambda e: (
                e.get("domain_trust_score", 0) + (4 if e.get("page_type") == "listing" else 0),
                e.get("domain_trust_score", 0),
            ),
            reverse=True,
        )
        return ranked[:count]
