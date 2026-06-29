# Final Build Plan: AI Accommodation Discovery Agent

**Date:** June 29, 2026
**Architecture:** Agentic, MCP-based, crawl-only, single EC2

---

## Core Architecture

```
User Query
    │
    ▼
┌──────────────────────────────────────┐
│  INPUT GUARDRAIL                      │
│  - Accommodation intent?             │
│  - PII / harmful content block       │
│  - Rate limit check                  │
│  (if blocked → short-circuit)        │
└──────────────────────────────────────┘
    │
    ▼
FastAPI (entry point)
    │
    ├─── LangGraph Agent (orchestrator)
    │      │
    │      │  Graph nodes:
    │      │  ┌─────────┐   ┌──────────┐   ┌─────────┐
    │      │  │ PLAN    │──→│ EXECUTE  │──→│ EVALUATE│──┐
    │      │  │ (Claude │   │ (tool    │   │ (has    │  │
    │      │  │ plans   │   │  calls)  │   │ enough? │  │
    │      │  │ steps)  │   │          │   │ need    │  │
    │      │  └─────────┘   └──────────┘   │ more?)  │  │
    │      │                               └────┬─────┘  │
    │      │  ┌────────────────┐                  │       │
    │      │  │ SYNTHESIZE     │←─────────────────┘       │
    │      │  │ (Claude builds │      (if done)           │
    │      │  │  answer)       │                           │
    │      │  └────────────────┘                           │
    │      │  ↑                                            │
    │      │  └────────────────────────────────────────────┘
    │      │            (if needs more data, re-plan)
    │
    ├─── MCP Server (embedded, SSE transport)
    │      ├── search_web(query)        → Brave Search API
    │      ├── scrape_url(url)          → FireCrawl API
    │      ├── extract_property(text)   → Bedrock Claude
    │      ├── search_es(query)         → Elasticsearch
    │      ├── store_property(data)     → Elasticsearch
    │      ├── search_cache(query)      → Redis
    │      └── synthesize_answer(data)  → Bedrock Claude
    │
    └─── Redis
           ├── Job queue + status (polling)
           └── Semantic cache (cosine sim > 0.90)
    │
    ▼
┌──────────────────────────────────────┐
│  OUTPUT GUARDRAIL                     │
│  - Grounding: cited sources exist?   │
│  - PII / toxic content strip         │
│  - Source URL verification           │
└──────────────────────────────────────┘
    │
    ▼
Frontend
```

## Stages

### Stage 1: Project Scaffold
- Python project skeleton (`pyproject.toml`, `src/` layout)
- `docker-compose.yml`: ES 8.x, Redis, FastAPI dev server
- `Makefile` with dev/test/lint commands
- Health-check endpoint stubs

### Stage 2: MCP Server
- `mcp-server/` package with `FastMCP` setup
- All tool stubs returning mock data
- SSE transport, registered via tool decorators
- Shared Pydantic models in `models.py`

### Stage 3: Web Tools (Brave + FireCrawl)
- `tools/brave_search.py` — search_web(query) → [urls]
- `tools/firecrawl.py` — scrape_url(url) → markdown
- Rate limiting, error handling, API key management

### Stage 4: Bedrock Integration
- `tools/extraction.py` — extract_property(markdown) → structured JSON
- `tools/synthesize.py` — synthesize_answer(properties) → conversational response
- `embedding.py` — Titan embedding for cache + ES vector search
- Prompt templates in `prompts/`

### Stage 5: Elasticsearch Tools
- `tools/es.py` — search_es(query) + store_property(data) + cleanup
- ES index mapping (geo_point, dense_vector 1536d, text, keyword)
- Time-based indices (properties-YYYY.MM.DD), 24hr TTL
- Hybrid query: knn + geo_distance + term/range + BM25 match

### Stage 6: Redis — Cache + Jobs
- `tools/cache.py` — search_cache(query) + store_cache(query, response)
- `src/jobs/` — job status store (Redis hash)
- Semantic cache: Titan embedding → cosine > 0.90 → return cached
- Job polling: search_id → status polling endpoint

### Stage 7: Agent Orchestrator (LangGraph)
- `src/agent/graph.py` — LangGraph state graph definition
- `src/agent/nodes/plan.py` — PLAN node: Claude receives query + state, outputs structured plan (list of steps)
- `src/agent/nodes/execute.py` — EXECUTE node: calls MCP tools based on current plan step
- `src/agent/nodes/evaluate.py` — EVALUATE node: Claude checks if results are sufficient → "done" or "needs more"
- `src/agent/nodes/synthesize.py` — SYNTHESIZE node: builds final answer from collected data

**Graph flow:**
```
PLAN → EXECUTE → EVALUATE → (if done → SYNTHESIZE, if needs more → PLAN again)
```

**LangGraph state:**
```python
class AgentState(TypedDict):
    query: str                    # original user query
    plan: list[dict]              # planned steps { tool, args, reason }
    completed_steps: list[dict]   # executed steps + results
    accumulated_data: list[dict]  # properties collected so far
    iteration: int                # prevent infinite loops
    max_iterations: int = 5
    response: str | None          # final answer
```

- **Tool integration:** LangGraph nodes call MCP tools via the MCP client (SSE). LangGraph manages state routing, MCP manages tool execution.
- **Grounding:** System prompt in PLAN + EVALUATE nodes enforces "only cite data you retrieved"
- **Stopping:** max 5 plan-execute-evaluate cycles, or EVALUATE returns "done"

### Stage 8: Guardrails
- Two guard points: pre-agent (input) and post-agent (output)
- Fast, cheap checks — no expensive LLM calls in the guard path

**Input Guardrail:**
- `src/guardrails/input_guard.py`
- Intent classifier: cheap Claude call or keyword model → "is this accommodation related?"
- PII/regex block: emails, phones, profanity in the query
- Rate limit: in-memory per-IP counter (100 req/min)
- Rejected queries return a short-circuit response, never reach the agent

**Output Guardrail:**
- `src/guardrails/output_guard.py`
- Grounding check: parse cited property IDs/titles from the synthesized response → verify each exists in the scraped result set → strip any hallucinated citations
- PII/toxic scan: regex + lightweight filter on the output before streaming
- Source URL verification: ensure every cited listing has a valid `source_url` in the result set

**Prompt integration:**
- Agent system prompt includes grounding rules
- Tool definitions include a `retrieved_from` field on every property so the agent can reference it

### Stage 9: API Layer
- `POST /api/search` — return `{ search_id }` (async, cache-first)
- `GET /api/search/{id}/status` — "queued" | "searching" | "scraping" | "extracting" | "complete"
- `GET /api/search/{id}/results` — SSE stream of final answer
- `GET /api/health` — ES + Redis status

### Stage 10: Frontend
- Vite + React + TypeScript + Tailwind
- Search input + status display + streaming results
- Property cards with source links
- Polls status every 3s during crawl

### Stage 11: Deployment
- S3 bucket → frontend static files
- CloudFront → /api/* → EC2, /* → S3
- EC2 t3.micro user-data: nginx + FastAPI + ES + Redis systemd
- GitHub Actions: frontend → S3 sync, backend → git pull + restart
- No Lambda, no API Gateway, no DynamoDB

---

## Tech Stack

| Component | Choice |
|---|---|
| API Framework | FastAPI (uvicorn) |
| MCP Framework | `mcp` Python SDK (FastMCP) |
| Agent Framework | LangGraph (plan → execute → evaluate loop) |
| LLM | Bedrock Claude 3 Sonnet via `langchain-aws` |
| Embeddings | Bedrock Titan v2 via `langchain-aws` (1536d) |
| Search Engine | Elasticsearch 8.x (self-hosted) |
| Cache/Queue | Redis |
| URL Discovery | Brave Search API |
| Scraper | FireCrawl API |
| Frontend | Vite + React + TypeScript + Tailwind |
| CDN | CloudFront |
| Storage | S3 (frontend + images) |
| Compute | EC2 t3.micro (free tier) |

---

## Entity Model (simple)

```
CrawledProperty
├── property_id: str (UUID)
├── source_url: str
├── source_site: str
├── title: str
├── description: str
├── location: { lat: float, lon: float, address: str }
├── price_monthly: float | None
├── bedrooms: int | None
├── bathrooms: int | None
├── amenities: list[str]
├── tags: list[str]
├── images: list[str] (S3 URLs)
├── reviews_summary: str | None
├── embedding: list[float] (1536d)
└── crawled_at: datetime
```
