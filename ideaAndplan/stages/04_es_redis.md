# Stage 4: Elasticsearch + Redis Persistence Layer

**Goal:** Production-grade persistence with ES for property search and Redis for caching, job tracking, and idempotency.

---

## Files Added

```
src/infrastructure/persistence/
├── elasticsearch/
│   └── repository.py     # CrawledPropertyESRepository
└── redis/
    ├── cache.py           # CacheRepository
    ├── job_repo.py        # JobRepository
    └── idempotency.py     # IdempotencyRepository
```

---

## ES Repository (`CrawledPropertyESRepository`)

### Index Strategy: Time-Based Indices

Index name pattern: `{prefix}-YYYY.MM.DD`

Example: `properties-2026.06.30`

Each index has a 24-hour lifespan. Data expires naturally as older indices are unused. A future cleanup cron can delete indices older than N days.

### Mapping (strict, dynamic: false)

| Field | ES Type | Notes |
|---|---|---|
| `property_id` | `keyword` | |
| `source_url` | `keyword` | |
| `source_site` | `keyword` | |
| `title` | `text` | Full-text search |
| `description` | `text` | Full-text search |
| `location` | `geo_point` | lat/lon pair |
| `address` | `text` | From location.address |
| `price_monthly` | `float` | Range queries |
| `bedrooms` | `integer` | |
| `bathrooms` | `integer` | |
| `amenities` | `keyword` | |
| `tags` | `keyword` | |
| `images` | `keyword` | URLs, not re-hosted |
| `reviews_summary` | `text` | |
| `embedding` | `dense_vector` | 1024d (Titan v2) |
| `crawled_at` | `date` | |
| `confidence` | `float` | |

### Methods

```python
async def ensure_index() -> None
async def store(property: CrawledProperty) -> None
async def search_hybrid(query: SearchQuery, embedding: list[float]) -> list[CrawledProperty]
async def delete_old_indices(retention_days: int = 2) -> int
```

### Search Behavior

Hybrid search using:
1. `multi_match` query across `title`, `description`, `reviews_summary`, `address`
2. Optional `term` filters for `bedrooms` (≥), `price_monthly` (≤)
3. Optional `geo_distance` filter for location
4. Optional `terms` filter for `tags`
5. Optional `knn` query if embedding is provided
6. Sorted by `_score` descending

---

## Redis Repositories

### CacheRepository

Stores synthesized responses with their query embeddings for similarity-based cache hits.

**Key pattern:**
- `cache:{sha256_of_query_bytes}` → JSON `{query, response, embedding, created_at}`

**Methods:**
```python
async def store(query: str, embedding: list[float], response: str, ttl: int) -> None
async def get_similar(query: str, threshold: float, embedding: list[float] | None = None) -> dict | None
```

`get_similar` generates an embedding (from BedrockClient if available, or uses the provided one) and scans cached entries. Returns the best match above `threshold` by cosine similarity. Falls back to exact match if no embedding service.

### JobRepository

Tracks async search job progress.

**Key pattern:**
- `job:{search_id}` → JSON `CrawlJob`

**Methods:**
```python
async def create(job: CrawlJob) -> None
async def update(search_id: str, **updates) -> CrawlJob | None
async def get(search_id: str) -> CrawlJob | None
```

### IdempotencyRepository

Ensures each `Idempotency-Key` is processed exactly once.

**Key pattern:**
- `idem:{key}` → `"in_progress"` | `"completed:{response_hash}"`

**Methods:**
```python
async def try_acquire(key: str, ttl: int) -> bool  # Returns False if already in progress
async def complete(key: str, response_hash: str) -> None
async def get_status(key: str) -> str | None  # None, "in_progress", or "completed:{hash}"
```

---

## Server Wiring

In `api/server.py`, the persistence repositories are instantiated from ES and Redis clients and injected into `ToolDependencies`:

```python
search_repo = CrawledPropertyESRepository(es, settings.es_index_prefix)
cache_repo = CacheRepository(redis, bedrock_client, settings.redis_cache_ttl)
job_repo = JobRepository(redis)
idem_repo = IdempotencyRepository(redis)

deps = ToolDependencies(
    search_repo=search_repo,
    cache_repo=cache_repo,
    job_repo=job_repo,
    idem_repo=idem_repo,
    ...
)
```

The MCP tools for `search_es`, `store_property`, `search_cache`, and `store_cache` now use real persistence instead of stubs.
