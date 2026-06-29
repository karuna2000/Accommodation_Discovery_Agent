# Development Plan: Stage by Stage

**Date:** June 29, 2026
**Goal:** Free-tier POC of AI-Powered Accommodation Discovery Platform

---

## Stage 1: Project Scaffold & Local Dev Environment
**Goal:** Working local dev environment with all services containerized.

### Steps
- Python project skeleton (pyproject.toml, src/ layout)
- Docker-compose with:
  - Elasticsearch 8.x
  - Redis
  - FastAPI dev server (hot-reload)

### Engineering Decisions
- **FastAPI on EC2** — everything runs as a single FastAPI app on the t3.micro. No Lambda wrappers needed for this architecture (no API Gateway, no DynamoDB Streams).
- **Project structure:** Domain-driven layout (`src/crawler/`, `src/search/`, `src/ai/`, `src/cache/`, `src/api/`).
- **Dependency management:** pip + requirements.txt for simplicity.
- **ES 8.x:** Official ES Docker image with security disabled for local dev.

### Deliverables
- `docker-compose.yml` (ES, Redis, FastAPI)
- `Makefile` with common commands (dev, test, lint)
- FastAPI app that starts and health-checks all dependencies
- Placeholder test suite

---

## Stage 2: Web Crawler — Search + Scrape + Extract
**Goal:** Given a user query, find relevant listings on the web and extract structured data.

### Steps
- Brave Search API integration — find listing URLs from query
- FireCrawl API integration — scrape each URL (handles JS rendering, anti-bot)
- LLM extraction pipeline — for each page, extract structured property data
- Crawled data model (Pydantic)

### Engineering Decisions
- **Brave Search API** to find candidate URLs. Query is the user's natural language query (e.g. "apartment for rent near UCLA under $1500"). Get top 10-15 results.
- **FireCrawl over Playwright:** FireCrawl is a managed API that handles JS rendering, anti-bot bypass, and returns clean Markdown/HTML. No headless browser to run on the t3.micro — saves ~500MB RAM and removes a major dependency. Free tier: 500 credits/month.
- **LLM extraction per page:** Pass FireCrawl's rendered Markdown to Claude with a structured extraction prompt. Output: `{ title, price, location, bedrooms, amenities, description, reviews_summary, images: [urls], source_url, source_site }`.
- **FireCrawl scrape endpoint:** Use `/scrape` for individual page extraction (returns clean markdown). No need for the crawl endpoint since Brave handles URL discovery.
- **Concurrency:** FireCrawl handles rate limits server-side. We fire up to 5 concurrent scrape requests.

### Crawl Flow
```
User Query → Brave Search API → [url1, url2, ..., url10]
                                    ↓
For each URL:
  FireCrawl /scrape → LLM extract from Markdown
                                    ↓
                        Structured property data
```

### Deliverables
- `src/crawler/discovery.py` — Brave Search URL discovery
- `src/crawler/scraper.py` — FireCrawl scrape client
- `src/crawler/extractor.py` — LLM extraction from page text
- `src/models/property.py` — CrawledProperty Pydantic model

---

## Stage 3: Elasticsearch Index — Store & Query Crawled Data
**Goal:** Store crawled property data in ES with 24hr TTL, enable hybrid search.

### Steps
- Define ES index mapping (geo_point, dense_vector, text, keyword)
- Index management script (create, delete, refresh)
- Index crawled properties after extraction
- Implement 24hr TTL via `@timestamp` + scheduled cleanup (or ES ILM)

### Engineering Decisions
- **No DynamoDB** — ES is the only data store. Crawled data lives only in ES.
- **24hr TTL:** Use `_created_at` timestamp field on every document. A periodic background task (cron every hour) deletes documents older than 24h. Alternatively, ES Index Lifecycle Management (ILM) with a 1-day rollover — but ILM is simpler with time-based indices.
- **Time-based indices approach:** `properties-YYYY.MM.DD`. Query across last 2 days. Delete indices older than 2 days. Simplifies TTL enforcement — delete the entire index.
- **Hybrid search mapping:** Same as before — geo_point for location, dense_vector for embeddings, text for description/title, keyword for amenities/tags.

### ES Index Mapping (v1)
```json
{
  "mappings": {
    "properties": {
      "property_id": { "type": "keyword" },
      "source_url": { "type": "keyword" },
      "source_site": { "type": "keyword" },
      "title": { "type": "text", "analyzer": "english" },
      "description": { "type": "text", "analyzer": "english" },
      "location": { "type": "geo_point" },
      "price_monthly": { "type": "float" },
      "bedrooms": { "type": "integer" },
      "amenities": { "type": "keyword" },
      "tags": { "type": "keyword" },
      "reviews_summary": { "type": "text" },
      "embedding": { "type": "dense_vector", "dims": 1536, "index": true, "similarity": "cosine" },
      "crawled_at": { "type": "date" }
    }
  }
}
```

### Deliverables
- `src/search/index_manager.py` — ES index management (daily indices)
- `src/search/index_service.py` — Index crawled properties, generate embeddings
- `src/search/query_service.py` — Hybrid query builder + executor
- `src/search/cleanup.py` — Delete old indices (>2 days)

---

## Stage 4: AI Search Agent — Intent + Synthesis
**Goal:** Natural language accommodation search. User asks, agent searches ES, synthesizes answer.

### Steps
- Intent parsing prompt + Claude call (extract filters from query)
- ES query builder (translate intent into ES DSL)
- Synthesis prompt + Claude call (results → conversational answer)
- SSE streaming endpoint

### Engineering Decisions
- **3-step single-turn flow** (no agentic loops):
  1. Intent → structured JSON (location, max_price, bedrooms, vibe)
  2. Structured JSON → ES hybrid query → ranked results
  3. Results → conversational summary via Claude
- **Hybrid query strategy:**
  - `knn` on `embedding` for semantic similarity to query
  - `geo_distance` filter on `location` if user specifies an area
  - `term`/`range` filters on `price_monthly`, `bedrooms`
  - `match` on `description`/`title` for BM25 keyword relevance
- **Streaming (SSE):** `text/event-stream` via FastAPI `StreamingResponse`. Streams token-by-token from Claude.
- **No synthesis cached in ES** — the synthesis is generated on-the-fly from stored results. The raw crawled data is what's cached in ES.

### Search Flow
```
User query "quiet studio near university under $700"
       ↓
Check ES for recent crawled results matching this query
       ↓
  ┌── If ES has results (from previous crawl <24h old):
  │    → Claude synthesis from existing data → stream response
  │
  └── If ES has no/few results:
       → Return { search_id, status: "crawling", message: "Searching..." }
       → Background crawl task (Stage 2)
       → Student polls GET /api/search/{search_id}/status
       → When crawl done → synthesize → student retrieves via
         GET /api/search/{search_id}/results
```

### Deliverables
- `src/ai/intent_parser.py` — Query → structured JSON
- `src/ai/query_builder.py` — JSON → ES DSL
- `src/ai/synthesizer.py` — Results → conversational response
- `src/api/search_router.py` — Search endpoint + polling endpoints
- `src/ai/prompts.py` — All prompt templates

---

## Stage 5: Background Crawl Processing
**Goal:** Handle async crawl jobs: track status, manage queue, update when done.

### Steps
- Job/task data model (search_id, status, progress, results_ref)
- Redis-based job queue + status store
- Background worker using FastAPI `BackgroundTasks` + thread pool
- Polling endpoints for frontend

### Engineering Decisions
- **Redis as job store:** `search:<search_id>` hash with `status` (queued/crawling/extracting/indexing/complete/error), `progress`, `created_at`, `result_count`.
- **Background worker:** For POC simplicity, use Python `asyncio.create_task` or `threading.Thread` within the FastAPI process. On a single t3.micro, this avoids needing Celery/RQ. The crawl task runs in the background while the API remains responsive.
- **Concurrency:** Max 2 concurrent crawl jobs on the t3.micro. Queue additional jobs.
- **Polling vs push:** Polling is simpler — frontend polls `GET /api/search/{search_id}/status` every 5s. No WebSocket needed for POC.
- **Graceful degradation:** If crawl fails for a URL, log it and continue with remaining URLs. Don't fail the entire job.

### Job States
```
queued → crawling → extracting → indexing → complete
                                  ↓
                               error (partial results may still exist)
```

### Deliverables
- `src/jobs/models.py` — Job status data model
- `src/jobs/store.py` — Redis-backed job store
- `src/jobs/worker.py` — Background crawl orchestrator
- `src/api/job_router.py` — Status + results polling endpoints

---

## Stage 6: Semantic Caching (Redis)
**Goal:** Avoid re-running the full search+crawl pipeline for similar queries.

### Steps
- Generate embedding for user query (Bedrock Titan)
- Check Redis for semantically similar cached responses
- Cache hit → return instantly (~20ms)
- Cache miss → run full pipeline → cache result

### Engineering Decisions
- **Two-level cache:**
  1. **Semantic cache (Redis):** Caches the final synthesized response for a query embedding. TTL: 24h (same as ES data). Threshold: cosine sim > 0.90.
  2. **ES data cache:** Already covered — crawled property data in ES with 24hr TTL.
- **Cache key:** Hash of query embedding vector. Store mapping of `hash → { query, response, results_metadata, embedding, created_at }`.
- **Eviction:** TTL-based (24h). When ES data expires, the semantic cache entries referencing that data would be stale, so same TTL.

### Flow
```
Query arrives → Titan embedding → Check Redis for similar (cos > 0.90)
                                       ↓
          Hit → Return cached synthesized response
                                       ↓
          Miss → Run ES search → if results found → synthesize → cache → respond
                                       ↓
                If no results → start crawl job → poll → synthesize → cache → respond
```

### Deliverables
- `src/cache/semantic_cache.py` — Redis cache get/put with cosine similarity
- `src/cache/embedding_service.py` — Bedrock Titan embedding

---

## Stage 7: Guardrails & Safety
**Goal:** Block non-accommodation queries, ground responses in crawled data.

### Steps
- Input guard: LLM classifier (accommodation-related?)
- Output guard: grounding check + PII filter

### Engineering Decisions
- **Input guard:** Cheap Claude call with binary classification. "Does this query ask about accommodation/housing?" If no, return "I can only help with accommodation questions."
- **No JSON schema enforcement needed** — intent parser output is used internally, not exposed to user.
- **Output grounding:** Pass crawled property IDs in synthesis prompt. After generation, verify any cited property names/URLs exist in the result set.
- **PII filter:** Regex-based on synthesized output before streaming (emails, phones).
- **Rate limiter:** In-memory per-IP (100 req/min). Simple FastAPI middleware.

### Deliverables
- `src/guardrails/input_guard.py` — Intent classification
- `src/guardrails/output_guard.py` — Grounding + PII checks
- `src/middleware/rate_limit.py` — Rate limiting

---

## Stage 8: Frontend (React on S3 + CloudFront)
**Goal:** Clean search interface.

### Steps
- Scaffold Vite + React + TypeScript app
- Search input with submit
- Polling status display ("Searching...", "Crawling site 3/10...")
- Results display (property cards + synthesized summary)
- Image gallery from S3

### Engineering Decisions
- **Single page — search only:** No owner dashboard. No auth. Just a search bar and results view.
- **SSE for cached queries** (fast results), **polling for crawl queries** (async).
- **Tailwind CSS** for styling. No component library.
- **Vite + React + TypeScript.**

### Deliverables
- `frontend/` — React app
- Search page with input + results
- Status polling during crawl
- Property card component

---

## Stage 9: Deployment (S3 + CloudFront + EC2)
**Goal:** Deploy everything to AWS free tier.

### Steps
- S3 bucket for frontend static files + crawled images
- CloudFront distribution for frontend + API proxy
- EC2 t3.micro with FastAPI + ES + Redis
- User-data script for EC2 setup (install deps, pull code, start services)
- GitHub Actions CI/CD

### Engineering Decisions
- **No API Gateway, no Lambda** — all API traffic goes through CloudFront → EC2 directly. Simpler, no cold starts.
- **CloudFront behaviors:**
  - `/api/*` → proxy to EC2 (origin)
  - `/*` → S3 bucket (static files)
- **EC2 setup:** nginx reverse proxy → uvicorn (FastAPI). ES and Redis run as systemd services.
- **No headless browser on EC2** — FireCrawl handles JS rendering remotely. Saves ~500MB RAM.
- **S3 for images:** Crawled images uploaded with `image:<sha256>` key. Batch cleanup (delete keys older than 24h via lifecycle policy).
- **CI/CD:** GitHub Actions → rsync deploy to EC2 + restart FastAPI. Frontend → S3 sync + CloudFront invalidation.

### Architecture (Deployed)
```
Student Browser
       │
       ▼
  CloudFront
  ├── /api/* ──→ EC2 t3.micro
  │                  ├── nginx → FastAPI (uvicorn)
  │                  ├── Elasticsearch 8.x
  │                  └── Redis
  └── /* ──→ S3 (React app + images)
```

### Deliverables
- `deploy/user-data.sh` — EC2 bootstrap script
- `deploy/nginx.conf` — Reverse proxy config
- `deploy/setup.sh` — Script to create S3 + CloudFront
- `.github/workflows/deploy.yml` — CI/CD pipeline
- `frontend/` → S3 sync step

---

## Stage 10: Monitoring & Polish
**Goal:** Know what's happening in production.

### Steps
- CloudWatch agent on EC2 for logs + metrics
- Structured JSON logging (request_id, duration_ms, status)
- Basic dashboards (search latency, crawl stats, cache hit rate, ES health)
- Graceful error responses

### Engineering Decisions
- **Structured logging from day 1** — JSON logs with `structlog`.
- **Health endpoint:** `GET /api/health` — returns status of ES, Redis.
- **Fallback:** If ES is down, return 503 with "Search temporarily unavailable."

### Deliverables
- CloudWatch config for EC2
- `src/middleware/logging.py` — Request ID + structured logging
- `src/middleware/error_handler.py` — Consistent error responses
- Health endpoint

---

## Stage Priority Summary

| Stage | Priority | Depends On | Estimated Effort |
|---|---|---|---|
| 1. Project Scaffold | **P0** | — | 1 session |
| 2. Web Crawler | **P0** | Stage 1 | 2-3 sessions |
| 3. ES Index + TTL | **P0** | Stage 1 | 1 session |
| 4. AI Search Agent | **P0** | Stage 3 | 2 sessions |
| 5. Background Crawl Jobs | **P0** | Stage 2, 4 | 1-2 sessions |
| 6. Semantic Caching | **P1** | Stage 4 | 1 session |
| 7. Guardrails | **P1** | Stage 4 | 1 session |
| 8. Frontend | **P1** | Stage 4 | 2 sessions |
| 9. Deployment | **P2** | Stage 1-8 | 2 sessions |
| 10. Monitoring | **P2** | Stage 9 | 1 session |
