# Stage 3: Web Tools (Brave + FireCrawl) with Resilience

**Goal:** Real API clients for web search and scraping, wrapped with production-grade resilience patterns.

---

## What We Built

### Files Added

```
src/infrastructure/
├── resilience/
│   ├── circuit_breaker.py   # CircuitBreaker with 3 states (CLOSED/OPEN/HALF_OPEN)
│   ├── retry.py             # retry_with_backoff() with exponential backoff + jitter
│   ├── timeout.py           # with_timeout() wrapping asyncio.wait_for
│   └── bulkhead.py          # Bulkhead with asyncio.Semaphore
└── external/
    ├── brave.py             # Brave Search API client
    ├── firecrawl.py         # FireCrawl API client
    └── bedrock.py           # Bedrock client (Claude + Titan)
```

---

## Resilience Pattern

Each external client wraps its calls with: **Timeout → Retry → Circuit Breaker → Bulkhead**

```
call() → Bulkhead.acquire() → CircuitBreaker.call() → Retry → Timeout → HTTP
```

The order matters:
1. **Bulkhead** — limits concurrent calls (reject early if saturated)
2. **Circuit Breaker** — rejects fast if service is known to be down
3. **Retry** — retries transient failures with backoff
4. **Timeout** — ensures we don't hang forever

### CircuitBreaker

```python
class CircuitState(Enum):
    CLOSED = "closed"     # Normal operation
    OPEN = "open"         # Failing — reject fast
    HALF_OPEN = "half_open"  # Testing recovery
```

- **CLOSED** → after `failure_threshold` failures → **OPEN**
- **OPEN** → after `recovery_timeout` seconds → **HALF_OPEN**
- **HALF_OPEN** → allows 1 call. Success → **CLOSED**. Failure → **OPEN**

Raises `CircuitBreakerOpenError` when OPEN, propagates original exception otherwise.

### Retry with Backoff

```
delay = min(base_delay * (2^attempt), max_delay)
delay += random.uniform(0, delay * 0.1)  # jitter
```

Only retries `retryable_exceptions` (TimeoutError, ConnectionError, HTTP 429/503). Non-retryable errors (400, 401, 403) fail immediately.

### Bulkhead

Simple asyncio.Semaphore wrapper. Configurable max concurrent calls per service.

---

## Brave Search Client

**Endpoint:** `GET https://api.search.brave.com/res/v1/web/search`

**Key decisions:**
- Rate limiting: max 1 req/s (free tier constraint)
- Returns top N result URLs from web search results
- Filters to accommodation-relevant results (optional, handled by the query)

```python
class BraveClient:
    async def search(self, query: str, count: int = 10) -> list[str]:
        # Wrapped: bulkhead → circuit breaker → retry → timeout
        # Returns clean URLs from search results
```

### FireCrawl Client

**Endpoint:** `POST https://api.firecrawl.com/v1/scrape`

**Key decisions:**
- Scrapes a single URL and returns clean markdown
- Handles JS rendering on the FireCrawl side
- No browser dependency on our EC2

```python
class FirecrawlClient:
    async def scrape(self, url: str) -> str:
        # Wrapped: bulkhead → circuit breaker → retry → timeout
        # Returns page content as markdown
```

### Bedrock Client

**Key decisions:**
- Claude Sonnet as primary, Haiku as fallback
- Titan Embeddings v2 for vector generation
- `invoke_with_fallback()` tries Sonnet → Haiku on failure

```python
class BedrockClient:
    PRIMARY = "anthropic.claude-3-sonnet-20240229-v1:0"
    FALLBACK = "anthropic.claude-3-haiku-20240307-v1:0"

    async def invoke_with_fallback(
        self, prompt: str, system: str = "",
    ) -> str:
        # Tries PRIMARY, catches timeout/circuit open, tries FALLBACK
        # Raises only if both fail

    async def generate_embedding(self, text: str) -> list[float]:
        # Titan Embeddings v2 via Bedrock

    async def extract_property(self, markdown: str, url: str) -> CrawledProperty:
        # Claude extraction prompt → structured JSON

    async def synthesize(self, properties: list[dict], query: str) -> str:
        # Claude synthesis prompt → conversational response
```

---

## How Tools Use Real Clients

The MCP tool stubs already check for real clients:

```python
# src/mcp/tools/brave_search.py
async def run(self, query: str, count: int = 10) -> list[str]:
    if self._deps.brave_client:
        return await self._deps.brave_client.search(query, count=count)
    return [f"https://example.com/mock-{i}" for i in range(count)]
```

Now that `self._deps.brave_client` is a real `BraveClient` instance with resilience, the tool calls the real API. If the API is unavailable or the circuit is open, the stub behavior is a fallback (though in production, the agent would see an error and try alternatives).

### Dependencies in ToolDependencies

`ToolDependencies` now receives:

```python
deps = ToolDependencies(
    brave_client=BraveClient(api_key, bulkhead, breaker),
    firecrawl_client=FirecrawlClient(api_key, bulkhead, breaker),
    bedrock_client=BedrockClient(settings, breaker),
    ...
)
```

## How to Verify

```python
# With env vars set:
client = BraveClient(api_key="...")
urls = await client.search("studio near UCLA")
print(urls)  # → ['https://...', ...]
```

## Key Decisions

| Decision | Rationale |
|---|---|
| **Resilience wrappers are generic** | Can be reused for any external service. Not coupled to Brave/FireCrawl specifics. |
| **Brave → FireCrawl → Bedrock layered** | Each client wraps its own bulkhead + breaker. A Bedrock outage doesn't affect Brave searches. |
| **Sonnet → Haiku fallback** | Haiku is 1/5th the cost and fast enough for synthesis + extraction. Sonnet preferred for planning and evaluation. |
| **Mock fallback in tools** | If a client fails to initialize (no API key), the tool returns mock data instead of crashing. Graceful degradation. |
| **Retry only transient failures** | 4xx errors (bad request, auth failure) fail fast. Only network errors, timeouts, and 429/503 are retried. |
