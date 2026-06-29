# Architecture Decision Record

**Date:** June 29, 2026
**Status:** Decided (Revised — Pure Crawl-Based)

---

## Architecture Overview

Pure crawl-based accommodation discovery. No owner ingestion, no student accounts, no transactional database (DynamoDB). Everything flows through: **web crawl → LLM extract → ES cache → AI synthesize**.

### Key Changes from v1
- ❌ DynamoDB — removed. ES is the only data store.
- ❌ API Gateway + Lambda — removed. Everything runs on a single EC2.
- ❌ Owner CRUD / Owner UI — removed. No owner-side at all.
- ❌ Student accounts, favorites, reviews — removed.
- ✅ Web crawler (Brave Search + FireCrawl) — added.
- ✅ Async crawl job system with polling — added.
- ✅ ES as 24hr rotating cache — added.
- ✅ S3 for temporary image storage — added.

---

## System Architecture

```
                        ┌──────────────────────────┐
                        │     Student Browser       │
                        │   (React on S3 + CF)      │
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
                     ┌──────────────────────────────────┐
                     │        EC2 t3.micro               │
                     │                                   │
                     │  ┌──────────────────────────┐    │
                     │  │  nginx → FastAPI (uvicorn) │    │
                     │  │  - POST /api/search        │    │
                     │  │  - GET  /api/search/{id}   │    │
                     │  │  - GET  /api/search/{id}/  │    │
                     │  │         results            │    │
                     │  └──────────────────────────┘    │
                     │                                   │
                     │  ┌──────────────────────────┐    │
                     │  │  Elasticsearch 8.x         │    │
                     │  │  Daily indices:            │    │
                     │  │  properties-YYYY.MM.DD     │    │
                     │  │  TTL: 2 days (auto-delete) │    │
                     │  │  Hybrid: geo+vector+BM25   │    │
                     │  └──────────────────────────┘    │
                     │                                   │
                     │  ┌──────────────────────────┐    │
                     │  │  Redis                     │    │
                     │  │  - Job queue + status      │    │
                     │  │  - Semantic cache (cosine) │    │
                     │  └──────────────────────────┘    │
                     │                                   │
                     └──────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌──────────┐    ┌──────────┐    ┌──────────┐
             │ Brave     │    │ Listing  │    │  S3      │
             │ Search    │    │ Sites    │    │ (Images) │
             │ API       │    │ (Airbnb, │    │          │
             │           │    │ Zillow,  │    │ TTL:24h  │
             └──────────┘    │ etc.)    │    └──────────┘
                             └──────────┘

External APIs:
  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
  │ Bedrock       │    │ Brave Search     │    │ FireCrawl        │
  │ Claude+ Titan │    │ API (free $5/mo) │    │ API (JS-render,  │
  └──────────────┘    └──────────────────┘    │ scrape)          │
                                              └──────────────────┘
```

---

## Request Lifecycle

### Cache Hit (Fast Path)
```
POST /api/search { query: "studio near UCLA under $1000" }
        ↓
FastAPI → generate Titan embedding → Redis semantic check
        ↓
  Cosine > 0.90? → Return cached synthesized response (~20ms)
```

### Cache Miss, ES Has Data
```
POST /api/search { query: "studio near UCLA under $1000" }
        ↓
Redis miss → ES hybrid query (knn + geo + filters + BM25)
        ↓
Results found (from previous crawl <24h old)
        ↓
Claude synthesis from results → SSE stream to client
        ↓
Cache synthesized response in Redis
```

### Cache Miss, No ES Data (Requires Crawl)
```
POST /api/search { query: "studio near UCLA under $1000" }
        ↓
Redis miss → ES query → no/few results
        ↓
Return { search_id: "abc123", status: "crawling" }
        ↓  (background)
Brave Search API → [url1, url2, ..., url10]
        ↓
For each URL (concurrent, max 2):
  FireCrawl scrape → LLM extract → index into ES
        ↓
All done → mark job complete in Redis
        ↓
Frontend polls GET /api/search/abc123 → status: "complete"
        ↓
GET /api/search/abc123/results → Claude synthesis → stream
```

---

## Data Model

### CrawledProperty (stored in ES)
```
{
  property_id: str (uuid)
  source_url: str
  source_site: str (e.g., "airbnb", "zillow", "craigslist")
  title: str
  description: str
  location: { lat: float, lon: float, address: str }
  price_monthly: float | null
  currency: str
  bedrooms: int | null
  bathrooms: int | null
  amenities: list[str]
  tags: list[str]              # LLM-generated
  images: list[str]            # S3 URLs
  reviews_summary: str         # LLM-summarized from page
  embedding: list[float]       # 1536-dim Titan embedding
  crawled_at: datetime (ISO8601)
}
```

### SearchJob (stored in Redis)
```
search:<id> → Hash {
  query: str
  status: "queued" | "crawling" | "extracting" | "indexing" | "complete" | "error"
  progress: { crawled: 5, total: 10 }
  result_count: int
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

---

## AWS Services Used

| Service | Purpose | Free Tier |
|---|---|---|
| EC2 t3.micro | FastAPI + ES + Redis | 750 hrs/mo |
| S3 | React frontend + crawled images | 5GB |
| CloudFront | CDN for frontend + API proxy | 1TB |
| Bedrock | Claude + Titan embeddings | $200 credits |
| CloudWatch | Logging + monitoring | 5GB logs |
| IAM | Permissions | Free |

**Not used:** DynamoDB, API Gateway, Lambda, SQS, Comprehend, Textract, Secrets Manager.

---

## Key Tradeoffs

| Decision | Rationale |
|---|---|
| **Single EC2 for everything** | Simplest deployment, free tier, single point of failure (acceptable for POC) |
| **ES as only data store** | No sync complexity. ES handles search + storage + TTL. Risk: ES downtime = no data. |
| **No DynamoDB** | No owner data to persist long-term. All data is temporary (24h). |
| **FireCrawl over Playwright** | FireCrawl handles JS rendering + anti-bot bypass as a managed API. No headless browser on EC2 saves RAM and complexity. |
| **Brave Search for URL discovery** | Free tier ($5/mo credits), good web search API, no custom crawler needed for discovery. |
| **Polling over WebSocket** | Simpler to implement and debug. 5s polling is fine for a search-async pattern. |
| **Background thread in FastAPI** | No need for Celery/RQ on a single-instance POC. Async task within the same process. |
| **Time-based ES indices** | Deleting old indices is simpler and cheaper than _delete_by_query for TTL enforcement. |
