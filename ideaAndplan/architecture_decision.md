# Architecture Decision Record

**Date:** July 1, 2026
**Status:** Decided (v3 — Pure Crawl-Based, Self-Hosted, Agentic)

---

## Architecture Overview

Pure crawl-based accommodation discovery. No owner ingestion, no student accounts, no transactional database. Everything flows through: **web crawl → LLM extract → ES cache → LangGraph agent → AI synthesize**. All search and scraping infrastructure is self-hosted alongside the API on a single EC2 via docker-compose.

### Key Changes from v1
- ❌ DynamoDB — removed. ES is the only data store.
- ❌ API Gateway + Lambda — removed. Everything runs on a single EC2.
- ❌ Owner CRUD / Owner UI — removed. No owner-side at all.
- ❌ Student accounts, favorites, reviews — removed.
- ❌ S3 image rehosting — removed. Images reference original source URLs only.
- ❌ Brave Search API — replaced by self-hosted SearXNG.
- ❌ FireCrawl API — replaced by self-hosted Crawl4AI.
- ❌ Claude / Titan Bedrock models — replaced by Amazon Nova Micro (LLM) + Cohere Embed v4 (embeddings); Claude blocked (Anthropic use case form required).
- ✅ Self-hosted search (SearXNG) + scraping (Crawl4AI) — added.
- ✅ LangGraph agent with PLAN → EXECUTE → EVALUATE → SYNTHESIZE loop — added.
- ✅ MCP server (FastMCP) for tool decoupling — added.
- ✅ Resilience stack (CircuitBreaker + Bulkhead + RetryWithBackoff + Timeout) — added on every external client.
- ✅ SSE streaming with Idempotency-Key deduplication — added.
- ✅ Heuristic regex extractor as permanent fallback — added.
- ✅ Guardrails (input classifier, rate limiter, PII stripper, output grounding) — added.

---

## System Architecture

```
                        ┌──────────────────────────┐
                        │     Student Browser       │
                        │   (React on S3 + CF)      │
                        │   Tailwind v4 + shadcn/ui │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │       CloudFront          │
                        │  /api/* → EC2             │
                        │  /*      → S3             │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                     ┌──────────────────────────────────────────┐
                     │           EC2 t3.micro                    │
                     │                                           │
                     │  ┌──────────────────────────────────┐    │
                     │  │  FastAPI (uvicorn, port 8000)      │    │
                     │  │  ├─ POST /api/search (SSE stream) │    │
                     │  │  ├─ POST /api/search/{id}/cancel  │    │
                     │  │  ├─ GET  /health                  │    │
                     │  │  └─ FastMCP SSE transport          │    │
                     │  │     (7 tools, embedded in-process) │    │
                     │  │                                     │    │
                     │  │  Agent: LangGraph StateGraph        │    │
                     │  │  PLAN → EXECUTE → EVALUATE          │    │
                     │  │       → SYNTHESIZE                  │    │
                     │  │  Nodes: intent, plan (static 5-    │    │
                     │  │  step), execute, evaluate,         │    │
                     │  │  synthesize, validate               │    │
                     │  │                                     │    │
                     │  │  Guardrails:                        │    │
                     │  │  ├─ Input: classifier + rate limiter│    │
                     │  │  └─ Output: PII stripper +          │    │
                     │  │     LLM grounding validator         │    │
                     │  └──────────────────────────────────┘    │
                     │                                           │
                     │  ┌─────────────────────────────┐        │
                     │  │  Resilience Wrappers         │        │
                     │  │  (every external client)     │        │
                     │  │  CircuitBreaker + Bulkhead   │        │
                     │  │  + RetryWithBackoff + Timeout│        │
                     │  └─────────────────────────────┘        │
                     │                                           │
                     │  ┌─────────────────────────────┐        │
                     │  │  Elasticsearch 8.x           │        │
                     │  │  indices: properties-YYYY.   │        │
                     │  │  MM.DD (TTL: 24h auto-      │        │
                     │  │  delete via curator or ILM)  │        │
                     │  │  Hybrid: vector+BM25         │        │
                     │  └─────────────────────────────┘        │
                     │                                           │
                     │  ┌─────────────────────────────┐        │
                     │  │  Redis 7                     │        │
                     │  │  ├─ Idempotency keys (24h)   │        │
                     │  │  ├─ Semantic cache (cosine)  │        │
                     │  │  ├─ Job state (search_jobs)  │        │
                     │  │  └─ Cost counters (daily)    │        │
                     │  └─────────────────────────────┘        │
                     │                                           │
                     │  ┌─────────────────────────────┐        │
                     │  │  SearXNG (port 8080)         │        │
                     │  │  Engines: DuckDuckGo,        │        │
                     │  │  Startpage, Wikipedia        │        │
                     │  │  (replaces Brave Search)     │        │
                     │  └─────────────────────────────┘        │
                     │                                           │
                     │  ┌─────────────────────────────┐        │
                     │  │  Crawl4AI (port 11235)       │        │
                     │  │  JS-rendered page scraping   │        │
                     │  │  → markdown output           │        │
                     │  │  (replaces FireCrawl)        │        │
                     │  └─────────────────────────────┘        │
                     │                                           │
                     └──────────────────────────────────────────┘
                                     │
                                     ▼
                     ┌──────────────────────────┐
                     │   Bedrock (us-east-1)     │
                     │  ├─ Nova Micro (LLM)      │
                     │  │  $0.035/1M tokens      │
                     │  └─ Cohere Embed v4       │
                     │     (embeddings)           │
                     └──────────────────────────┘
```

---

## Request Lifecycle

### 1. Cache Hit (Fast Path)
```
POST /api/search { query, Idempotency-Key }
        ↓
Idempotency check → previously completed?
        ↓
Generate Cohere embedding → Redis semantic cache
        ↓
Cosine > 0.90? → Return cached synthesized answer via SSE
```

### 2. Cache Miss, ES Has Data
```
POST /api/search { query, Idempotency-Key }
        ↓
Redis miss → ES hybrid query (knn + BM25 + filters)
        ↓
Results found (from previous crawl <24h old)
        ↓
LangGraph agent runs:
  PLAN → EXECUTE → EVALUATE → SYNTHESIZE
        ↓
Nova Micro synthesizes answer from results
→ SSE stream to client
        ↓
Cache synthesized response in Redis
```

### 3. Cache Miss, No ES Data (Full Crawl)
```
POST /api/search { query, Idempotency-Key }
        ↓
Redis miss → ES query → no/few results
        ↓
LangGraph PLAN node:
  Static 5-step plan (hardcoded):
  1. search_web(query, count=8)
  2. scrape(url_1)
  3. scrape(url_2)
  4. extract(url_1, markdown_1)
  5. extract(url_2, markdown_2)
        ↓
EXECUTE node:
  $variable resolution (result_url_N, markdown_N)
  SearXNG → [result_url_1..result_url_8]
  Crawl4AI scrapes top 2 URLs → markdown
  Nova Micro / heuristic fallback extracts structured data
  → indexes into ES
        ↓
EVALUATE node:
  Validate extracted properties, check for errors
        ↓
SYNTHESIZE node:
  Nova Micro synthesizes conversational response
  → SSE stream to client
        ↓
Cache response in Redis
```

---

## Data Model

### CrawledProperty (stored in ES)
```
{
  property_id: str (uuid)
  source_url: str
  source_site: str (e.g., "magicbricks", "99acres")
  title: str
  description: str
  location: { lat: float, lon: float, address: str }
  price_monthly: float | null
  currency: str
  bedrooms: int | null
  bathrooms: int | null
  amenities: list[str]
  tags: list[str]              # LLM/heuristic-generated
  images: list[str]            # Original source URLs (no rehosting)
  rating: float | null         # Heuristic/LLM extracted
  reviews_summary: str         # LLM-summarized from page
  embedding: list[float]       # 1024-dim Cohere Embed v4
  crawled_at: datetime (ISO8601)
}
```

### SearchJob (stored in Redis)
```
search_jobs:<id> → Hash {
  query: str
  status: "queued" | "crawling" | "extracting" | "indexing" | "complete" | "error"
  progress: { crawled: 5, total: 10 }
  result_count: int
  agent_state: str (JSON-serialized AgentState from LangGraph)
  created_at: datetime
  completed_at: datetime | null
}
```

### CacheEntry (stored in Redis)
```
cache:<hash> → Hash {
  query: str
  query_embedding: list[float]
  response: str (synthesized answer)
  result_ids: list[str] (property IDs referenced)
  created_at: datetime
}
TTL: 24 hours
```

### IdempotencyEntry (stored in Redis)
```
idempotency:<key> → Hash {
  status_code: int
  headers: dict
  body: str
  created_at: datetime
}
TTL: 24 hours
```

---

## AWS Services Used

| Service | Purpose | Free Tier |
|---|---|---|
| EC2 t3.micro | FastAPI + ES 8.x + Redis 7 + SearXNG + Crawl4AI (5 docker-compose services) | 750 hrs/mo |
| S3 | React frontend static hosting (no image storage) | 5GB |
| CloudFront | CDN for frontend + `/api/*` proxy to EC2 | 1TB |
| Bedrock | Nova Micro ($0.035/1M tokens) + Cohere Embed v4 | $200 credits |
| Route53 | Custom domain for CloudFront (Stage 7) | 50 hosted zones |
| CloudWatch | Application logging + monitoring | 5GB logs |
| IAM | Permissions / instance profile | Free |

**Not used:** DynamoDB, API Gateway, Lambda, SQS, Comprehend, Textract, Secrets Manager, S3 image rehosting.

---

## Key Tradeoffs

| Decision | Rationale |
|---|---|
| **Single EC2 for everything** | Simplest deployment, free tier, single point of failure (acceptable for POC). 5 services in docker-compose. |
| **Self-hosted SearXNG over Brave Search** | No API key dependency, no $5/mo credit cap, unlimited queries. Downside: DuckDuckGo rate-limits, Google blocked. Startpage + Wikipedia as fallback engines. |
| **Self-hosted Crawl4AI over FireCrawl** | No API key, no 500-credit/mo cap, runs on same EC2. Downside: RAM usage (~256MB per crawl). |
| **LangGraph agent over linear pipeline** | Enables plan–execute–evaluate loop, retry on failure, cross-step variable resolution (`$markdown_N`). Overkill for simple queries but extensible. |
| **Static 5-step plan (no LLM planning)** | Nova Micro outputs unreliable/unparseable plan format. Hardcoded plan is simpler and deterministic. |
| **MCP server for tool decoupling** | Tools (search, scrape, extract, synthesize, cache, ES) are independent, testable, and swappable via FastMCP SSE transport. |
| **Resilience wrappers on every client** | CircuitBreaker prevents cascade failures; Bulkhead limits concurrency; RetryWithBackoff handles transient failures; Timeout prevents hangs. All configurable per service. |
| **Heuristic regex extractor as fallback** | Heuristic extraction (prices ₹/Rs/$/£/€, bedrooms 2BHK/Studio, amenities AC/WiFi) runs even when Bedrock is unavailable. |
| **SSE streaming over polling** | Real-time progress during agent execution (crawling → extracting → synthesizing). `Idempotency-Key` prevents duplicate work. |
| **Time-based ES indices** | Deleting old indices is simpler/cheaper than `_delete_by_query`. Properties expire in 24h. |
| **Nova Micro over Claude** | Claude models blocked by AWS (Anthropic use case form required). Nova Micro is cheaper ($0.035/1M) and works immediately. |
| **Cohere Embed v4 over Titan** | Cohere has a dedicated embedding inference profile (`us.cohere.embed-v4:0`). Titan Embeddings (`amazon.titan-embed-text-v2:0`) unused. |
| **Guardrails on input + output** | Input: query classifier (off-topic detection) + rate limiter (100 req/min). Output: PII stripping (phone, email, SSN) + LLM grounding validation. |
| **No image rehosting on S3** | Reduces storage cost and transfer. Source URLs may break, but acceptable for POC. |
| **aioboto3 for async Bedrock** | Native async SDK for Bedrock runtime. Supports both Nova (messages.content[].text) and Claude (anthropic_version) formats. |
