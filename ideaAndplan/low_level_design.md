# Low-Level Design

**Date:** June 29, 2026

---

## 1. Package Structure

```
src/
├── main.py                          # FastAPI app entry + DI
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic BaseSettings (env vars)
│
├── domain/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── property.py              # CrawledProperty
│   │   ├── search.py                # SearchQuery, SearchResult
│   │   └── job.py                   # CrawlJob, JobStatus enum
│   └── ports/
│       ├── __init__.py
│       ├── search_repository.py     # Abstract interface for ES
│       ├── cache_repository.py      # Abstract interface for Redis
│       ├── job_repository.py        # Abstract interface for job store
│       └── scraper_service.py       # Abstract interface for Brave+FireCrawl
│
├── infrastructure/
│   ├── __init__.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── elasticsearch/
│   │   │   ├── __init__.py
│   │   │   ├── client.py            # ES client singleton factory
│   │   │   ├── repository.py        # SearchRepository impl
│   │   │   └── index_manager.py     # Create indices, TTL cleanup
│   │   └── redis/
│   │       ├── __init__.py
│   │       ├── client.py            # Redis client singleton factory
│   │       ├── cache_repository.py  # CacheRepository impl
│   │       └── job_repository.py    # JobRepository impl
│   └── external/
│       ├── __init__.py
│       ├── brave.py                 # Brave Search API client
│       ├── firecrawl.py             # FireCrawl API client
│       └── bedrock.py               # Bedrock LLM + embeddings
│
├── mcp/
│   ├── __init__.py
│   ├── server.py                    # FastMCP server + tool registration
│   ├── registry.py                  # Auto-discovery + tool factory
│   └── tools/
│       ├── __init__.py
│       ├── base.py                  # BaseTool ABC
│       ├── brave_search.py          # search_web(query) → [url]
│       ├── firecrawl.py             # scrape_url(url) → markdown
│       ├── extraction.py            # extract_property(markdown) → CrawledProperty
│       ├── es.py                    # search_es(query) → [CrawledProperty]
│       ├── cache.py                 # search_cache(query) → response | None
│       └── synthesize.py            # synthesize_answer([CrawledProperty]) → str
│
├── agent/
│   ├── __init__.py
│   ├── state.py                     # AgentState TypedDict
│   ├── graph.py                     # LangGraph StateGraph definition
│   ├── prompts.py                   # System/user prompt templates
│   └── nodes/
│       ├── __init__.py
│       ├── plan.py                  # PLAN node
│       ├── execute.py               # EXECUTE node
│       ├── evaluate.py              # EVALUATE node
│       └── synthesize.py            # SYNTHESIZE node
│
├── guardrails/
│   ├── __init__.py
│   ├── input/
│   │   ├── __init__.py
│   │   ├── pipeline.py              # Chain of InputGuard protocols
│   │   ├── intent_classifier.py     # "is this accommodation related?"
│   │   └── content_filter.py        # PII/profanity regex block
│   └── output/
│       ├── __init__.py
│       ├── pipeline.py              # Chain of OutputGuard protocols
│       ├── grounding.py             # Verify cited sources exist
│       └── content_filter.py        # Strip PII/toxic content
│
├── api/
│   ├── __init__.py
│   ├── server.py                    # FastAPI app factory
│   ├── dependencies.py              # DI via FastAPI Depends()
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── search.py                # POST /api/search, GET /{id}/status, /{id}/results
│   │   └── health.py                # GET /api/health
│   └── middleware/
│       ├── __init__.py
│       ├── logging.py               # Request ID + structlog
│       ├── rate_limit.py            # In-memory per-IP rate limiter
│       └── error_handler.py         # Consistent JSON error format
│
└── common/
    ├── __init__.py
    ├── errors.py                    # Domain exceptions
    └── types.py                     # Shared type aliases
```

---

## 2. SOLID Principles Application

### S — Single Responsibility

| Module | Responsibility |
|---|---|
| `mcp/tools/brave_search.py` | One job: call Brave Search API, return URLs |
| `infrastructure/persistence/elasticsearch/repository.py` | One job: CRUD operations on ES |
| `guardrails/input/intent_classifier.py` | One job: classify query as accommodation or not |
| `agent/nodes/plan.py` | One job: receive state, output plan |
| `api/routes/search.py` | One job: HTTP route handlers, delegate to services |
| `config/settings.py` | One job: load and validate environment config |

### O — Open/Closed

- **New tool →** add a file in `mcp/tools/`, implement `BaseTool`, register it. No existing code changes.
- **New guard →** implement the guard protocol, add to pipeline list. Pipeline iterates over guards; no pipeline code change.
- **New storage backend →** implement `SearchRepository` interface. Existing code depends on the interface, not the implementation.
- **New LLM provider →** implement `LLMService` protocol in `infrastructure/external/`. Agent depends on the protocol.

### L — Liskov Substitution

All implementations of an interface are interchangeable:

```python
# Any SearchRepository impl can be swapped in
class SearchRepository(ABC):
    @abstractmethod
    async def search(self, query: SearchQuery) -> list[CrawledProperty]: ...
    @abstractmethod
    async def store(self, property: CrawledProperty) -> None: ...

class ElasticsearchRepository(SearchRepository): ...
class InMemoryRepository(SearchRepository): ...  # for tests
```

### I — Interface Segregation

Small, focused port interfaces instead of one big "DataPort":

```python
# Instead of one monolithic port:
class SearchPort(ABC):          # Only search operations
    async def search(...)...
class StoragePort(ABC):         # Only write operations
    async def store(...)...
class IndexManagementPort(ABC): # Only admin operations
    async def create_index(...)...
    async def cleanup(...)...
```

### D — Dependency Inversion

High-level modules (agent, api) depend on abstractions (ports), not concretions:

```
 Agent               API Routes
  │                     │
  ▼                     ▼
 Port interfaces (domain/ports/)
  │                     │
  ▼                     ▼
 Infrastructure implementations
```

Agent never imports `elasticsearch-py` or `redis-py`. It only imports port interfaces. Concrete implementations are injected at startup via DI container.

---

## 3. Design Patterns

### 3.1 Repository Pattern

Abstraction over data storage, used for both ES and Redis.

```python
# domain/ports/search_repository.py
class SearchRepository(ABC):
    @abstractmethod
    async def search_hybrid(
        self, query: SearchQuery, embedding: list[float]
    ) -> list[CrawledProperty]: ...

    @abstractmethod
    async def store(self, property: CrawledProperty) -> None: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...

# infrastructure/persistence/elasticsearch/repository.py
class ElasticsearchRepository(SearchRepository):
    def __init__(self, client: Elasticsearch, index_name: str):
        self._client = client
        self._index = index_name

    async def search_hybrid(self, query, embedding):
        # Build ES DSL: knn + geo + bool filters
        ...

    async def store(self, property):
        await self._client.index(index=self._index, ...)
```

### 3.2 Strategy Pattern

Used for pluggable algorithms — guard strategies, scraping strategies.

```python
# guardrails/input/pipeline.py
class InputGuard(Protocol):
    async def check(self, query: str) -> GuardResult: ...

class InputGuardPipeline:
    def __init__(self, guards: list[InputGuard]):
        self._guards = guards

    async def run(self, query: str) -> GuardResult:
        for guard in self._guards:
            result = await guard.check(query)
            if not result.allowed:
                return result
        return GuardResult(allowed=True)
```

Guards implement the protocol independently:

```python
class IntentClassifier:
    async def check(self, query: str) -> GuardResult: ...

class ContentFilter:
    async def check(self, query: str) -> GuardResult: ...

class RateLimiter:
    async def check(self, query: str) -> GuardResult: ...
```

### 3.3 Factory Pattern

Tool registry uses factory to instantiate tools with their dependencies.

```python
# mcp/registry.py
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, type[BaseTool]] = {}

    def register(self, tool_cls: type[BaseTool]):
        self._tools[tool_cls.name] = tool_cls

    def create_all(self, deps: Dependencies) -> list[BaseTool]:
        return [cls(deps) for cls in self._tools.values()]

# Registration via decorator
@registry.register
class BraveSearchTool(BaseTool):
    name = "search_web"
    ...
```

### 3.4 Chain of Responsibility

Guardrails are processed as a chain. Each guard can short-circuit.

```
Input Guard Pipeline:
  query → IntentClassifier → ContentFilter → RateLimiter
          ↓ blocked        ↓ blocked      ↓ blocked
          return           return          return

Output Guard Pipeline:
  response → GroundingCheck → ContentFilter → final response
            ↓ failed        ↓ stripped
            return error     return cleaned
```

### 3.5 Adapter Pattern

Each MCP tool is an adapter that wraps an external API into a uniform interface.

```python
# mcp/tools/base.py
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict  # JSON Schema

    @abstractmethod
    async def run(self, **kwargs) -> Any: ...

# mcp/tools/brave_search.py
class BraveSearchTool(BaseTool):
    name = "search_web"
    description = "Search the web for accommodation listings"

    def __init__(self, deps: Dependencies):
        self._client = deps.brave_client

    async def run(self, query: str, count: int = 10) -> list[str]:
        return await self._client.search(query, count=count)
```

### 3.6 State Pattern

LangGraph's `StateGraph` naturally implements the State pattern. Each node is a state handler.

```python
# agent/graph.py
workflow = StateGraph(AgentState)

workflow.add_node("plan", PlanNode(deps))
workflow.add_node("execute", ExecuteNode(deps))
workflow.add_node("evaluate", EvaluateNode(deps))
workflow.add_node("synthesize", SynthesizeNode(deps))

workflow.add_edge("plan", "execute")
workflow.add_edge("execute", "evaluate")
workflow.add_conditional_edges(
    "evaluate",
    router,          # "done" → synthesize, "needs_more" → plan
    {"done": "synthesize", "needs_more": "plan"}
)
workflow.set_entry_point("plan")
```

### 3.7 Dependency Injection

All dependencies are wired at startup in `main.py`, injected via constructors and FastAPI `Depends()`.

```python
# main.py
@app.on_event("startup")
async def startup():
    settings = Settings()

    # --- Infrastructure clients ---
    es_client = await create_es_client(settings)
    redis_client = await create_redis_client(settings)
    brave_client = BraveClient(
        api_key=settings.brave_api_key,
        bulkhead=Bulkhead("brave", settings.brave_max_concurrent),
        breaker=CircuitBreaker("brave", settings.brave_cb_failure_threshold, settings.brave_cb_recovery_timeout),
    )
    firecrawl_client = FirecrawlClient(
        api_key=settings.firecrawl_api_key,
        bulkhead=Bulkhead("firecrawl", settings.firecrawl_max_concurrent),
        breaker=CircuitBreaker("firecrawl", settings.firecrawl_cb_failure_threshold, settings.firecrawl_cb_recovery_timeout),
    )
    bedrock = BedrockClient(
        settings=settings,
        breaker=CircuitBreaker("bedrock", settings.bedrock_cb_failure_threshold, settings.bedrock_cb_recovery_timeout),
    )

    # --- Repositories ---
    search_repo = ElasticsearchRepository(es_client)
    cache_repo = RedisCacheRepository(redis_client)
    job_repo = RedisJobRepository(redis_client)
    idem_repo = RedisIdempotencyRepository(redis_client, ttl=settings.idempotency_ttl)

    # --- DI container ---
    deps = Dependencies(
        search_repo=search_repo,
        cache_repo=cache_repo,
        job_repo=job_repo,
        idem_repo=idem_repo,
        brave_client=brave_client,
        firecrawl_client=firecrawl_client,
        bedrock=bedrock_client,
    )

    app.state.idem_repo = idem_repo
    agent_graph = create_agent_graph(deps)   # LangGraph
    mcp_server = create_mcp_server(deps)     # FastMCP
    app.state.deps = deps
    app.state.agent = agent_graph
```

```python
# api/dependencies.py
async def get_deps(request: Request) -> Dependencies:
    return request.app.state.deps

async def get_agent(request: Request) -> CompiledStateGraph:
    return request.app.state.agent
```

---

## 4. Idempotency

### Problem
If the client retries the same request (network glitch, timeout), the system would start a second crawl — wasting Brave Search credits, FireCrawl credits, Bedrock tokens, and time.

### Solution: `Idempotency-Key` Header

Standard pattern (used by Stripe, Shopify). The client sends a unique key with the request. The server deduplicates by key.

```
POST /api/search
Idempotency-Key: 7c8e9a1f-3d2b-4e5f-8a7b-6c5d4e3f2a1b
{ "query": "studio near UCLA under $1000" }
```

### Port Interface

```python
# domain/ports/idempotency_repository.py
@dataclass
class IdempotencyRecord:
    key: str
    response_status: int
    response_body: dict
    created_at: datetime

class IdempotencyRepository(ABC):
    @abstractmethod
    async def get(self, key: str) -> IdempotencyRecord | None: ...

    @abstractmethod
    async def store(
        self, key: str, status: int, body: dict, ttl: int
    ) -> None: ...
```

### Implementation (Redis)

```python
# infrastructure/persistence/redis/idempotency_repository.py
class RedisIdempotencyRepository(IdempotencyRepository):
    def __init__(self, redis: Redis, ttl: int = 86400):
        self._redis = redis
        self._ttl = ttl

    async def get(self, key: str) -> IdempotencyRecord | None:
        data = await self._redis.get(f"idempotency:{key}")
        if not data:
            return None
        return IdempotencyRecord(**json.loads(data))

    async def store(self, key: str, status: int, body: dict, ttl: int | None = None):
        record = IdempotencyRecord(
            key=key, response_status=status,
            response_body=body, created_at=datetime.utcnow()
        )
        await self._redis.setex(
            f"idempotency:{key}",
            ttl or self._ttl,
            record.model_dump_json()
        )
```

### Middleware (FastAPI)

```python
# api/middleware/idempotency.py
@app.middleware("http")
async def idempotency_middleware(request: Request, call_next):
    if request.method not in ("POST", "PATCH"):
        return await call_next(request)

    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        return await call_next(request)

    repo: IdempotencyRepository = request.app.state.idem_repo
    existing = await repo.get(idem_key)
    if existing:
        return JSONResponse(
            status_code=existing.response_status,
            content=existing.response_body,
            headers={"Idempotency-Replay": "true"}
        )

    response = await call_next(request)
    if response.status_code < 500:  # don't cache server errors
        body = await response.body()
        await repo.store(idem_key, response.status_code, json.loads(body))
    return response
```

### Behavior Table

| Scenario | Behavior |
|---|---|
| First request with key `X` | Process normally, store result keyed by `X` |
| Retry with same key `X` (prior in progress) | Wait and poll — or return `409 Conflict` with existing `search_id` |
| Retry with same key `X` (prior complete) | Return stored response immediately |
| Same query, different key `Y` | Treated as independent request (allowed — user may want fresh crawl) |
| Key `X` older than 24h | TTL expired, treated as new request |

---

## 5. Data Flow Per Request (with Idempotency)

```
POST /api/search
Idempotency-Key: abc-123
{ "query": "studio near UCLA under $1000" }
    │
    ▼
Idempotency middleware
    ├── [KEY EXISTS] → return stored response (Idempotency-Replay: true)
    │
    └── [NEW KEY] → continue
    │
    ▼
Input guardrail pipeline
    │→ IntentClassifier: "accommodation?" → yes
    │→ ContentFilter: no PII/profanity    → pass
    │→ RateLimiter: 5 req/min             → pass
    │
    ├─ [BLOCKED] → return 400/403 (stored under idem key)
    │
    └─ [PASS] → Semantic cache check
        │
        ├─ [HIT] → return cached { search_id, response } (stored under idem key)
        │
        └─ [MISS] → Create job (status: "queued")
                        → Store idempotency key → return { search_id, status: "queued" }
                        → Background: run agent graph
```

**Agent background execution:**

```
AgentState = {
    query: str,
    plan: [],
    completed_steps: [],
    accumulated_data: [],
    iteration: 0,
    response: None,
}

PLAN: Claude + state → structured plan
      e.g., ["search_web(studio near UCLA, count=10)",
             "scrape_url(url1)", ..., "extract_property(...)"]
      → state.plan = steps, state.iteration += 1

EXECUTE: For each step in state.plan:
            tool = mcp_server.tools[step.tool]
            result = await tool.run(**step.args)
            state.completed_steps.append({step, result})
            state.accumulated_data.extend(result.properties)
            job_store.update_progress(search_id, step_count)

EVALUATE: Claude + state → decision
          "done" | "needs_more" | "error"
          if "needs_more" and iteration < max → route to PLAN
          if "done" → route to SYNTHESIZE

SYNTHESIZE: Claude + accumulated_data → conversational response
            state.response = response
            cache_store.put(query, response)
            job_store.mark_complete(search_id, response)
```

**Client polling:**

```
Frontend polls every 3s:
  GET /api/search/{id}/status → { status, progress, response? }
    ├─ status: "queued" | "planning" | "searching" | "scraping" |
    │           "extracting" | "synthesizing" | "complete" | "error"
    │
    └─ when "complete": GET /api/search/{id}/results → SSE stream
```

---

## 6. Resilience

### 6.1 Design Principles

1. **Fail fast, degrade gracefully** — If a non-critical service fails, the system continues with reduced functionality. Only critical-path failures return errors to the user.
2. **Isolate failures** — A failure in one service should not cascade to others. Use circuit breakers, timeouts, and bulkheads.
3. **Retry transient failures** — Network blips, rate limits, and timeouts are retried with exponential backoff + jitter.
4. **Don't retry non-transient failures** — 4xx errors, auth failures, invalid input are returned immediately.

### 6.2 Service Dependency Map

```
                    ┌──────────────┐
                    │   API Route   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Redis     │ │ Guard    │ │ MCP      │
        │ (critical)│ │ (critical)│ │ Tools    │
        └──────────┘ └──────────┘ └────┬─────┘
                                       │
              ┌────────────┬───────────┼───────────┬──────────────┐
              ▼            ▼           ▼           ▼              ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Brave     │ │ FireCrawl│ │ Bedrock  │ │ ES       │ │ Redis    │
        │ (optional)│ │ (optional)││ (critical)││ (critical)││ (critical)│
        └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**Criticality legend:**
- **Critical** — If this fails, the request cannot be served. Error returned to user.
- **Optional** — If this fails, the agent can still produce a partial result or try alternatives.

### 6.3 Circuit Breaker Pattern

Per-service circuit breaker to stop hammering a failing service.

```python
# infrastructure/resilience/circuit_breaker.py
import asyncio
from enum import Enum
from datetime import datetime, timedelta

class CircuitState(Enum):
    CLOSED = "closed"        # normal operation
    OPEN = "open"            # failing, reject fast
    HALF_OPEN = "half_open"  # testing if recovered

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_calls = 0

    async def call(self, fn, *args, **kwargs):
        if self._state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
            else:
                raise CircuitBreakerOpenError(self.name)

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._half_open_calls = 0

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self._half_open_max_calls:
                self._state = CircuitState.OPEN
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def _should_attempt_recovery(self) -> bool:
        if not self._last_failure_time:
            return True
        elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
        return elapsed >= self._recovery_timeout
```

### 6.4 Per-Service Configuration

| Service | Timeout | Retries | Backoff | Circuit Breaker | Fallback |
|---|---|---|---|---|---|
| **Brave Search** | 10s | 3 | 1s × 2^attempt + jitter | 5 failures → open 30s | Return empty URL list → agent may try alternative search |
| **FireCrawl** | 30s | 3 | 2s × 2^attempt + jitter | 5 failures → open 60s | Skip failed URL, log warning, continue with remaining |
| **Bedrock (Claude)** | 60s | 2 | 2s × 2^attempt + jitter | 3 failures → open 60s | If cached response exists, return that with "stale" flag. Else return error. |
| **Bedrock (Titan)** | 15s | 2 | 1s × 2^attempt + jitter | 3 failures → open 30s | Cannot generate embedding → agent uses keyword-only search |
| **Elasticsearch** | 5s | 2 | 500ms × 2^attempt | 3 failures → open 10s | Return 503. Agent cannot function without search. |
| **Redis (cache)** | 2s | 1 | — | 3 failures → open 10s, degrade to no-cache mode | Skip cache, run full pipeline |
| **Redis (jobs)** | 2s | 2 | 500ms × 2^attempt | 3 failures → open 10s | Return 503. Job status tracking unavailable. |
| **Redis (idempotency)** | 2s | 1 | — | 3 failures → open 10s, skip dedup | Allow duplicate requests (degraded but functional) |

### 6.5 Retry with Exponential Backoff + Jitter

```python
# infrastructure/resilience/retry.py
import asyncio
import random

async def retry_with_backoff(
    fn, *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (TimeoutError, ConnectionError),
    **kwargs
):
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            await asyncio.sleep(delay + jitter)
    raise last_exception  # type: ignore
```

### 6.6 Timeout

Every external call uses `asyncio.wait_for` with a per-service timeout.

```python
# infrastructure/resilience/timeout.py
async def with_timeout(fn, *args, timeout: float, **kwargs):
    try:
        return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        raise ServiceTimeoutError(fn.__name__, timeout)
```

### 6.7 Bulkhead (Semaphore per Service)

Prevent one slow service from exhausting all worker threads.

```python
# infrastructure/resilience/bulkhead.py
class Bulkhead:
    def __init__(self, name: str, max_concurrent: int = 2):
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, fn, *args, **kwargs):
        async with self._semaphore:
            return await fn(*args, **kwargs)

# Example usage
bulkheads = {
    "brave": Bulkhead("brave", max_concurrent=2),
    "firecrawl": Bulkhead("firecrawl", max_concurrent=3),
    "bedrock": Bulkhead("bedrock", max_concurrent=1),  # Claude is expensive
}
```

### 6.8 Wrapped Client Pattern

Each external client wraps its calls with timeout + retry + circuit breaker + bulkhead:

```python
# infrastructure/external/brave.py
class BraveClient:
    def __init__(self, api_key: str, bulkhead: Bulkhead, breaker: CircuitBreaker):
        self._api_key = api_key
        self._bulkhead = bulkhead
        self._breaker = breaker

    async def search(self, query: str, count: int = 10) -> list[str]:
        async def _do_search():
            return await with_timeout(
                self._call_brave_api, query, count,
                timeout=10.0
            )

        return await retry_with_backoff(
            lambda: self._bulkhead.execute(
                lambda: self._breaker.call(_do_search)
            ),
            max_retries=3,
            base_delay=1.0
        )

    async def _call_brave_api(self, query: str, count: int) -> list[str]:
        # actual HTTP call to Brave Search API
        ...
```

### 6.9 Fallback LLM Strategy

| Node | Primary Model | Fallback Model | Failover Condition |
|---|---|---|---|
| **PLAN** | Claude Sonnet | Claude Haiku | Sonnet fails after retries → fallback to Haiku for plan generation |
| **EXECUTE** | — | — | Tool calls don't use LLM; they use circuit breakers |
| **EVALUATE** | Claude Sonnet | Claude Haiku | Sonnet fails → Haiku evaluates if data is sufficient |
| **SYNTHESIZE** | Claude Sonnet | Claude Haiku | Sonnet fails → Haiku builds the response (Haiku excels at structured→conversational) |
| **Extraction** | Claude Sonnet | Claude Haiku | Sonnet fails → Haiku extracts property data from markdown |

```python
# infrastructure/external/bedrock.py
class BedrockClient:
    PRIMARY_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
    FALLBACK_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"

    async def invoke_with_fallback(
        self, prompt: str, system: str,
        primary: str | None = None,
        fallback: str | None = None,
    ) -> str:
        models = [
            primary or self.PRIMARY_MODEL,
            fallback or self.FALLBACK_MODEL,
        ]
        last_error = None
        for model in models:
            try:
                return await retry_with_backoff(
                    self._invoke,
                    model_id=model,
                    prompt=prompt,
                    system=system,
                    max_retries=1,
                )
            except (ServiceTimeoutError, CircuitBreakerOpenError) as e:
                last_error = e
                logger.warning("llm_fallback", model=model, error=str(e))
                continue
        raise last_error  # type: ignore
```

**Rationale for Haiku:**
- 1/5th the cost of Sonnet
- Faster response times (critical for perceived latency)
- Synthesis is "reformat data into paragraphs" — Haiku handles this easily
- Plan generation and evaluation benefit from Sonnet's reasoning, but Haiku works as a fallback

### 6.10 Graceful Degradation Table

| Failed Service | Degraded Behavior |
|---|---|
| Brave Search | Return "Unable to search for listings right now. Try again later." |
| FireCrawl | Skip URLs that failed to scrape, return partial results with note |
| Bedrock (Claude) | If cache has a response, return with "This result was generated earlier." If no cache, return error. |
| Bedrock (Titan) | Fall back to keyword-only search (no semantic matching). Results will be less accurate but functional. |
| Elasticsearch | Return 503. System cannot function without search. |
| Redis (cache) | Skip cache. Every query runs the full pipeline. Slightly slower but functional. |
| Redis (jobs) | Return 503. Cannot track async jobs without job store. |
| Redis (idempotency) | Allow requests through without dedup. Risk of duplicate crawls. |

### 6.10 Domain Errors

```python
# common/errors.py
class AppError(Exception):
    def __init__(self, message: str, code: str, status: int = 500):
        self.message = message
        self.code = code
        self.status = status

# Guard errors
class QueryBlockedError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"Query blocked: {reason}", "QUERY_BLOCKED", 400)

class RateLimitError(AppError):
    def __init__(self):
        super().__init__("Rate limit exceeded", "RATE_LIMITED", 429)

# Service errors
class ServiceError(AppError):
    pass

class ServiceTimeoutError(ServiceError):
    def __init__(self, service: str, timeout: float):
        super().__init__(
            f"Service {service} timed out after {timeout}s",
            "SERVICE_TIMEOUT", 504
        )

class CircuitBreakerOpenError(ServiceError):
    def __init__(self, service: str):
        super().__init__(
            f"Service {service} is temporarily unavailable",
            "CIRCUIT_OPEN", 503
        )

class ToolExecutionError(AppError):
    def __init__(self, tool: str, detail: str):
        super().__init__(
            f"Tool {tool} failed: {detail}",
            "TOOL_ERROR", 502
        )

# Idempotency errors
class IdempotencyKeyReplayedError(AppError):
    def __init__(self, key: str):
        super().__init__(
            f"Request with key {key} is still in progress",
            "IDEMPOTENCY_IN_PROGRESS", 409
        )

# api/middleware/error_handler.py
@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.message, "code": exc.code}
    )
```

### 6.11 Agent-Level Resilience

Within the LangGraph agent loop, tool failures are handled at the node level:

| Node | On Tool Failure |
|---|---|
| **PLAN** | If Claude fails → retry once. If still fails → return error state. |
| **EXECUTE** | Catches `ServiceTimeoutError` / `CircuitBreakerOpenError`. Logs the failure. Sets `step.status = "skipped"`. Continues to next step. If all steps fail → EVALUATE returns "error". |
| **EVALUATE** | If Claude fails → retry once. Second failure → default to "done" if there's accumulated data, else "error". |
| **SYNTHESIZE** | If Claude fails → retry once. Second failure → return a plain JSON summary of accumulated data instead of conversational response. |

```python
# agent/nodes/execute.py
class ExecuteNode:
    async def __call__(self, state: AgentState) -> AgentState:
        for step in state.plan:
            try:
                tool = self._mcp.get_tool(step.tool)
                result = await tool.run(**step.args)
                state.completed_steps.append(StepResult(step=step, result=result, error=None))
                state.accumulated_data.extend(result.properties)
            except (ServiceTimeoutError, CircuitBreakerOpenError, ToolExecutionError) as e:
                logger.warning("tool_failed", tool=step.tool, error=str(e))
                state.completed_steps.append(StepResult(step=step, result=None, error=str(e)))
                # Continue to next step — don't fail the whole request
                continue
        return state
```

---

## 7. Additional Architectural Concerns

### 7.1 Legal & Compliance

| Risk | Mitigation | Decision |
|---|---|---|
| **Scraping ToS violation** | FireCrawl handles robots.txt and legal compliance on their end. We don't bypass access controls or scrape behind logins. Only scrape publicly accessible listing pages. | Accept risk. If a site blocks FireCrawl, we skip it. |
| **Image copyright** | Do NOT rehost scraped images on S3. Reference original image URLs from the source page. This avoids storing copyrighted content. | **No image storage.** Property cards display `source_url` for images, not S3 copies. |
| **PII in output** | Strip emails, phone numbers, and full names from scraped content at extraction time (not just at output guard). Store only anonymized data in ES. | Strip at extraction → verify at output guard. Two layers. |
| **GDPR / data retention** | All scraped data expires from ES after 24h (time-based index deletion). No long-term storage of any user data. | Built into TTL design. |
| **Terms of service** | Add a disclaimer: "This tool aggregates publicly available listings. Verify all information with the source." | Shown on frontend. |

### 7.2 Data Quality

#### Deduplication
The same property often appears on multiple sites (e.g., Zillow + Apartments.com). We need to detect and merge duplicates.

```python
# domain/ports/search_repository.py
class SearchRepository(ABC):
    # ...

    @abstractmethod
    async def find_duplicates(
        self, property: CrawledProperty, threshold: float = 0.95
    ) -> list[CrawledProperty]: ...
```

**Strategy:** Before storing a crawled property, check for near-duplicates by:
1. **Exact URL match** — already crawled this URL → skip
2. **Address similarity** — same lat/lng or address string within 50m → likely duplicate
3. **Title + price similarity** — same approximate title and price → merge

**Merge rule:** If duplicate found, keep the entry with more complete data. If both are equally complete, keep the earlier one (original crawl wins).

#### Sparse Data Handling
Most crawled listings will have missing fields. The schema must handle `None` gracefully.

```python
# domain/models/property.py
class CrawledProperty(BaseModel):
    property_id: str
    source_url: str
    source_site: str
    title: str
    description: str | None = None          # ← nullable
    location: Location | None = None         # ← nullable (geocoding may fail)
    price_monthly: float | None = None       # ← nullable (not all sites show price)
    bedrooms: int | None = None
    bathrooms: int | None = None
    amenities: list[str] = []
    tags: list[str] = []
    images: list[str] = []                   # ← original URLs, not S3
    reviews_summary: str | None = None
    embedding: list[float] | None = None
    crawled_at: datetime
    confidence: float = 0.5                  # how much of the data is populated
```

**Synthesis prompt instruction:** "If a property is missing a field, say it's not available rather than guessing. Only cite information that was explicitly extracted."

#### Price Normalization

```python
class PriceNormalizer:
    # Normalize to monthly USD
    NORMALIZATIONS = {
        "pw": lambda p: p * 4.33,       # per week → monthly
        "pn": lambda p: p,               # per night → keep as nightly (flag)
        "pcm": lambda p: p,              # per calendar month → as-is
    }

    @classmethod
    def normalize(cls, amount: float, period: str, currency: str) -> NormalizedPrice:
        if currency.upper() != "USD":
            # Try to detect and convert (or flag as non-USD)
            ...
        multiplier = cls.NORMALIZATIONS.get(period, lambda p: p)
        return NormalizedPrice(
            monthly_estimate=round(multiplier(amount), 0),
            original_amount=amount,
            original_period=period,
            confidence="exact" if period == "pcm" else "estimated",
        )
```

### 7.3 Context Window Management

Scraped pages + extracted data + prompt can easily exceed Claude's context window (200K tokens for Sonnet, but cheaper models have less).

**Strategy: Per-page summarization before synthesis.**

```python
# agent/nodes/execute.py
class ExecuteNode:
    MAX_PAGE_TOKENS = 8000  # truncate each page to ~8K tokens

    async def _process_page(self, url: str) -> CrawledProperty | None:
        markdown = await firecrawl_client.scrape(url)
        markdown = self._truncate(markdown, self.MAX_PAGE_TOKENS)
        return await extract_property(markdown)

    def _truncate(self, text: str, max_tokens: int) -> str:
        # Rough estimate: ~4 chars per token
        if len(text) > max_tokens * 4:
            # Truncate from the middle, keep beginning (title, price)
            # and end (reviews, contact info)
            ...
        return text
```

**Budget per search:**

| Component | Max Tokens |
|---|---|
| System prompt | ~500 |
| Each crawled property (summarized to ~100 words) | ~2,000 × 10 = ~20,000 |
| Synthesis prompt | ~500 |
| **Total per SYNTHESIZE call** | **~21,000** — well within Haiku's 48K context |

### 7.4 Cost Tracking

The free tier credits won't last forever. Track usage to avoid surprise bills.

```python
# infrastructure/monitoring/cost_tracker.py
@dataclass
class UsageRecord:
    service: str          # "bedrock", "brave", "firecrawl"
    model: str | None     # "claude-3-sonnet", "titan-v2", etc.
    tokens_in: int | None
    tokens_out: int | None
    cost: float           # estimated USD
    timestamp: datetime

class CostTracker:
    def __init__(self, redis: Redis):
        self._redis = redis
        self._prefix = "cost:"

    async def track(self, record: UsageRecord):
        key = f"{self._prefix}{record.service}:{datetime.utcnow().strftime('%Y-%m-%d')}"
        await self._redis.hincrbyfloat(key, "cost", record.cost)
        for field in ("tokens_in", "tokens_out"):
            if getattr(record, field) is not None:
                await self._redis.hincrby(key, field, getattr(record, field))

    async def get_daily_cost(self, service: str | None = None) -> dict:
        # Returns cost breakdown for today
        ...
```

**Cost budget alerts:** CloudWatch alarm if daily cost exceeds a threshold (e.g., $1/day).

**Bedrock cost estimation:**

| Model | Input / 1K tokens | Output / 1K tokens |
|---|---|---|
| Claude 3 Sonnet | $0.003 | $0.015 |
| Claude 3 Haiku | $0.00025 | $0.00125 |
| Titan Embeddings v2 | $0.00002 | — |

**Expected daily usage (estimated for POC):**

| Service | Calls/day | Daily cost |
|---|---|---|
| Bedrock Sonnet | ~50 | ~$0.50 |
| Bedrock Haiku | ~50 (fallback + extraction) | ~$0.02 |
| Bedrock Titan | ~100 | ~$0.002 |
| Brave Search | ~30 | ~$0.00 (free credits) |
| FireCrawl | ~200 | ~$0.00 (free credits) |
| **Total** | | **~$0.52/day → ~$15.60/month** |

At this rate, the $200 Bedrock credits last ~13 months. FireCrawl's 500 free credits/month may run out faster depending on page count.

### 7.5 Request Cancellation

If a user closes the tab mid-crawl, we should stop wasting credits.

```python
# api/routes/search.py
@router.post("/api/search/{search_id}/cancel")
async def cancel_search(search_id: str, deps: Depends(get_deps)):
    job = await deps.job_repo.get(search_id)
    if not job:
        raise HTTPException(404)

    await deps.job_repo.update_status(search_id, JobStatus.CANCELLED)

    # Signal the agent loop to abort
    await deps.cancel_registry.cancel(search_id)

    return {"status": "cancelled"}
```

```python
# infrastructure/resilience/cancellation.py
class CancellationRegistry:
    def __init__(self):
        self._events: dict[str, asyncio.Event] = {}

    def register(self, search_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[search_id] = event
        return event

    async def cancel(self, search_id: str):
        event = self._events.get(search_id)
        if event:
            event.set()

    def unregister(self, search_id: str):
        self._events.pop(search_id, None)
```

**Agent integration:**
```python
# agent/nodes/execute.py
class ExecuteNode:
    async def __call__(self, state: AgentState) -> AgentState:
        cancel_event = self._cancel_registry.register(state.search_id)
        for step in state.plan:
            if cancel_event.is_set():
                state.error = "Request cancelled by user"
                return state
            # ... execute step
        self._cancel_registry.unregister(state.search_id)
        return state
```

---

## 8. Configuration

```python
# config/settings.py
class Settings(BaseSettings):
    # AWS
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    # Elasticsearch
    es_host: str = "localhost"
    es_port: int = 9200
    es_index_prefix: str = "properties"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_cache_ttl: int = 86400  # 24 hours
    redis_cache_threshold: float = 0.90  # cosine similarity

    # External APIs
    brave_api_key: str
    firecrawl_api_key: str

    # Agent
    agent_max_iterations: int = 5
    agent_max_tool_calls: int = 20

    # Rate limiting
    rate_limit_per_minute: int = 100

    # Idempotency
    idempotency_ttl: int = 86400  # 24 hours

    # Resilience — circuit breakers
    brave_cb_failure_threshold: int = 5
    brave_cb_recovery_timeout: float = 30.0
    firecrawl_cb_failure_threshold: int = 5
    firecrawl_cb_recovery_timeout: float = 60.0
    bedrock_cb_failure_threshold: int = 3
    bedrock_cb_recovery_timeout: float = 60.0
    es_cb_failure_threshold: int = 3
    es_cb_recovery_timeout: float = 10.0
    redis_cb_failure_threshold: int = 3
    redis_cb_recovery_timeout: float = 10.0

    # Resilience — timeouts
    brave_timeout: float = 10.0
    firecrawl_timeout: float = 30.0
    bedrock_timeout: float = 60.0
    titan_timeout: float = 15.0
    es_timeout: float = 5.0
    redis_timeout: float = 2.0

    # Resilience — bulkheads
    brave_max_concurrent: int = 2
    firecrawl_max_concurrent: int = 3
    bedrock_max_concurrent: int = 1

    model_config = SettingsConfigDict(env_file=".env")
```

---

## 9. Testing Strategy

| Layer | Test type | Tool | What it tests |
|---|---|---|---|
| Domain models | Unit | pytest | Model validation, serialization |
| Port interfaces | Unit (with mocks) | pytest + unittest.mock | Interface contracts |
| Infrastructure | Integration | pytest + testcontainers | ES queries, Redis ops against real containers |
| MCP tools | Integration | pytest + httpx | Tool responses with real API (or sandbox) |
| Guardrails | Unit | pytest | Classification, regex, rate limiting |
| Agent nodes | Unit (with mocked tools) | pytest | Node logic, state transitions |
| Agent graph | Integration | pytest | Full plan-execute-evaluate cycle with mocked tools |
| API routes | Integration | httpx + pytest | Request/response, middleware, guards |
| End-to-end | E2E | pytest | Full flow: query → guard → agent → response |

---

## 10. Key Interfaces Summary

```python
# domain/ports/search_repository.py
class SearchRepository(ABC):
    @abstractmethod
    async def search_hybrid(
        self, query: SearchQuery, embedding: list[float]
    ) -> list[CrawledProperty]: ...

    @abstractmethod
    async def store(self, property: CrawledProperty) -> None: ...

    @abstractmethod
    async def store_batch(self, properties: list[CrawledProperty]) -> None: ...

    @abstractmethod
    async def count_recent(self, since: datetime) -> int: ...

    @abstractmethod
    async def delete_expired(self, before: datetime) -> int: ...

# domain/ports/cache_repository.py
class CacheRepository(ABC):
    @abstractmethod
    async def get_similar(self, embedding: list[float], threshold: float) -> str | None: ...

    @abstractmethod
    async def store(self, query: str, embedding: list[float], response: str, ttl: int) -> None: ...

# domain/ports/job_repository.py
class JobRepository(ABC):
    @abstractmethod
    async def create(self, job: CrawlJob) -> None: ...

    @abstractmethod
    async def get(self, job_id: str) -> CrawlJob | None: ...

    @abstractmethod
    async def update_status(self, job_id: str, status: JobStatus, **updates) -> None: ...

# domain/ports/scraper_service.py
class ScraperService(ABC):
    @abstractmethod
    async def discover_urls(self, query: str, count: int = 10) -> list[str]: ...

    @abstractmethod
    async def scrape_page(self, url: str) -> str: ...  # returns markdown
```
