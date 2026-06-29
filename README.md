# Accommodation Discovery Agent

AI-powered accommodation discovery platform. Crawls property listings from the web, extracts structured data, caches it in Elasticsearch, and serves conversational search results via an agentic LLM loop.

**Self-hosted search & scraping** — no third-party API dependencies. Uses SearXNG (meta-search) and Crawl4AI (web scraping) running in Docker alongside the API, Elasticsearch, and Redis.

---

## Architecture

```
User ──► React (Vite) ──► FastAPI ──► LangGraph Agent
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                          SearXNG     Crawl4AI    Bedrock
                         (search)    (scrape)    (LLM + embeddings)
                              │           │
                              ▼           ▼
                          Elasticsearch ◄──── properties cache
                          Redis ◄──── idempotency, jobs, cost
```

### Agent Loop (LangGraph)

```
PLAN ──► EXECUTE ──► EVALUATE ──► SYNTHESIZE ──► DONE
           │                          ▲
           └────── (loop back) ───────┘
```

1. **PLAN** — Hardcoded 5-step plan: search → scrape (×2) → extract (×2)
2. **EXECUTE** — Runs each step via MCP tools (search_web, scrape_url, extract_property)
3. **EVALUATE** — Decides whether to continue or synthesize
4. **SYNTHESIZE** — LLM generates conversational answer from extracted properties

---

## Features

- **Conversational search** — natural language queries for accommodation
- **Self-hosted infrastructure** — SearXNG (meta-search) + Crawl4AI (web scraping) in Docker
- **LLM-powered extraction** — Amazon Bedrock Nova Micro extracts structured property data from raw pages
- **Heuristic fallback** — regex-based property extractor when Bedrock is unavailable
- **Resilience stack** — per-service circuit breakers, bulkheads, timeouts, retry with exponential backoff + jitter
- **Idempotent requests** — Redis-backed `Idempotency-Key` header (24h TTL)
- **SSE streaming** — real-time agent progress and results via Server-Sent Events
- **Request cancellation** — `POST /api/search/{id}/cancel`
- **PII stripping** — at extraction and output
- **Data expiration** — time-based Elasticsearch indices (`properties-YYYY.MM.DD`)
- **Grounding check** — validates answer against extracted data
- **Input guardrails** — query validation + rate limiting

---

## Prerequisites

- Docker & Docker Compose
- AWS account with Bedrock access (Nova Micro model)
- AWS credentials (`~/.aws/credentials` or env vars)

### AWS Bedrock Models

| Model | Purpose | Status |
|-------|---------|--------|
| `us.amazon.nova-micro-v1:0` | Primary LLM | ✅ Works |
| `us.cohere.embed-v4:0` | Embeddings | ✅ Works |
| Claude models | Fallback LLM | ⛔ Requires [Anthropic use case form](https://docs.aws.amazon.com/bedrock/latest/userguide/model-use-case.html) |

---

## Setup

### 1. Clone & configure

```bash
git clone <repo>
cd Accommodation_Discovery_Agent
cp .env.example .env
```

Edit `.env` with your AWS region and Bedrock model IDs:

```env
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.amazon.nova-micro-v1:0
BEDROCK_EMBEDDING_MODEL_ID=us.cohere.embed-v4:0
```

### 2. AWS credentials (choose one)

**Option A — Profile** (default):
```bash
export AWS_PROFILE=default
# Mounts automatically via docker-compose (~/.aws:/root/.aws:ro)
```

**Option B — Access keys** (set in `.env`):
```env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

### 3. Start services

```bash
docker compose up --build
```

This starts all 5 services:
| Service | Port | Purpose |
|---------|------|---------|
| `api` | 8000 | FastAPI + agent |
| `elasticsearch` | 9200 | Property cache |
| `redis` | 6379 | Idempotency, jobs, caching |
| `searxng` | 8080 | Meta-search |
| `crawl4ai` | 11235 | Web scraping |

### 4. Start frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## Usage

### Web UI

Open `http://localhost:5173` and type a query like:
- *"Paying guest accommodations for boys near Hitech City Hyderabad"*
- *"2 BHK flat in Mansarovar Jaipur under 15000"*

### API

```bash
curl -N -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"query": "PG near Hitech City Hyderabad"}'
```

Streams SSE events:
```
data: {"type": "event", "data": {"plan": {"plan": "1. search_web(...)\n2. scrape_url(...)"}}}
data: {"type": "event", "data": {"execute": {"step_index": 0, "results": [...]}}}
data: {"type": "done", "search_id": "...", "answer": "Here are some properties..."}
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/search/{id}` | Search job status |
| `POST` | `/api/search/{id}/cancel` | Cancel running search |

### Makefile

```bash
make dev       # docker compose up --build
make test      # run tests
make lint      # ruff check
make clean     # docker compose down -v
make shell     # bash in api container
```

---

## Project Structure

```
├── docker-compose.yml          # 5 services: es, redis, searxng, crawl4ai, api
├── Dockerfile                  # Python 3.12-slim FastAPI container
├── pyproject.toml              # Python deps + config
├── requirements.txt            # Pinned deps
├── Makefile                    # dev/test/lint/clean shortcuts
├── .env.example                # Environment template
│
├── src/
│   ├── main.py                 # Entry point
│   ├── api/
│   │   ├── server.py           # FastAPI app factory, lifespan, clients
│   │   └── routes/
│   │       ├── health.py       # Health endpoint
│   │       └── search.py       # SSE streaming, cancel, status
│   ├── agent/
│   │   ├── graph.py            # LangGraph StateGraph (PLAN→EXECUTE→EVALUATE→SYNTHESIZE)
│   │   ├── state.py            # AgentState TypedDict
│   │   └── nodes/
│   │       ├── plan.py         # Static 5-step plan
│   │       ├── execute.py      # Tool execution + $variable resolution
│   │       ├── evaluate.py     # Loop decision (continue vs synthesize)
│   │       └── synthesize.py   # Bedrock answer generation
│   ├── mcp/
│   │   ├── server.py           # FastMCP server (SSE transport)
│   │   ├── registry.py         # Tool registry
│   │   └── tools/
│   │       ├── base.py         # Base tool + ToolDependencies
│   │       ├── brave_search.py # Web search (Brave API / SearXNG)
│   │       ├── firecrawl.py    # Web scrape (FireCrawl / Crawl4AI)
│   │       ├── extraction.py   # Property extraction (Bedrock + heuristic fallback)
│   │       └── synthesize.py   # Answer synthesis
│   ├── infrastructure/
│   │   ├── external/
│   │   │   ├── bedrock.py      # Bedrock client (Nova + Claude format)
│   │   │   ├── brave.py        # Brave Search client
│   │   │   ├── firecrawl.py    # FireCrawl client
│   │   │   ├── searxng.py      # Self-hosted SearXNG client
│   │   │   └── crawl4ai.py     # Self-hosted Crawl4AI client
│   │   ├── persistence/
│   │   │   ├── elasticsearch/  # Properties repository (time-based indices)
│   │   │   └── redis/          # Cache, idempotency, job repository
│   │   └── resilience/         # CircuitBreaker, Bulkhead, Retry, Timeout
│   ├── guardrails/
│   │   ├── input/              # Query validation, rate limiting
│   │   └── output/             # PII stripping, grounding checks
│   ├── config/settings.py      # Pydantic settings (env file + defaults)
│   ├── domain/models/          # Property, Job, Search models
│   └── common/errors.py        # AppError hierarchy
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Root component
│   │   ├── components/
│   │   │   ├── Chat.tsx        # Chat UI (messages, reasoning panel, suggestions)
│   │   │   └── ui/             # shadcn components (button, card, collapsible, etc.)
│   │   ├── hooks/
│   │   │   └── useSearch.ts    # SSE streaming, step tracking, state management
│   │   ├── types.ts            # TypeScript types
│   │   └── lib/utils.ts        # cn() utility
│   ├── vite.config.ts          # Vite + Tailwind v4 + API proxy
│   └── package.json            # React 18, shadcn, tailwindcss v4
│
└── tests/                      # 86 tests (pytest, async)
```

---

## Configuration

All settings via environment variables (`.env` or `docker-compose` env):

### Core
| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_PROFILE` | `default` | AWS profile name |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-micro-v1:0` | Primary LLM |
| `BEDROCK_EMBEDDING_MODEL_ID` | `us.cohere.embed-v4:0` | Embedding model |

### Infrastructure
| Variable | Default | Description |
|----------|---------|-------------|
| `ES_HOST` | `elasticsearch` | Elasticsearch host |
| `REDIS_HOST` | `redis` | Redis host |
| `SEARXNG_HOST` | `searxng` | SearXNG host |
| `CRAWL4AI_HOST` | `crawl4ai` | Crawl4AI host |

### Resilience
| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_TIMEOUT` | `60.0` | Bedrock request timeout (s) |
| `SEARXNG_TIMEOUT` | `15.0` | SearXNG request timeout |
| `CRAWL4AI_TIMEOUT` | `60.0` | Crawl4AI request timeout |
| `SEARXNG_MAX_CONCURRENT` | `3` | Max concurrent SearXNG requests |

Full list in `src/config/settings.py`.

---

## Testing

```bash
# All tests (86 passing)
make test

# Or directly
docker compose run --rm api pytest -v

# Lint
make lint
```

```bash
# Frontend typecheck
cd frontend && npm run typecheck

# Frontend build
cd frontend && npm run build
```

---

## Deployment

Target: single EC2 t3.micro with Docker Compose. Frontend on S3 + CloudFront, API proxied through CloudFront.

1. Deploy EC2 with Docker
2. `docker compose up -d` (all 5 services)
3. Build frontend: `cd frontend && npm run build`
4. Upload `frontend/dist/` to S3 bucket
5. Configure CloudFront → S3 for static assets, CloudFront → EC2:8000 for `/api/*`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, LangGraph, Pydantic |
| **AI/LLM** | Amazon Bedrock (Nova Micro, Cohere Embed), Claude (blocked) |
| **Search** | SearXNG (DuckDuckGo, Startpage, Wikipedia engines) |
| **Scraping** | Crawl4AI |
| **Cache & State** | Elasticsearch 8.x, Redis 7 |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS v4, shadcn/ui |
| **Infrastructure** | Docker Compose, EC2 t3.micro |

---

## Architecture Decisions

### Self-hosted by default
Brave Search and FireCrawl APIs exist as optional backends, but the default is self-hosted SearXNG for meta-search and Crawl4AI for web scraping. This removes all third-party API dependencies and keeps the system fully contained in `docker-compose up`.

### Single EC2 for everything
All services (FastAPI, ES, Redis, SearXNG, Crawl4AI) run on one EC2 t3.micro via Docker Compose. Simplest deployment, free tier eligible. Single point of failure is acceptable for a POC.

### ES as only data store, not DynamoDB
No owner data to persist long-term. All crawled data is temporary (24h TTL via time-based indices `properties-YYYY.MM.DD`). ES handles search + storage + TTL in one place.

### No DynamoDB, no API Gateway, no Lambda
Removed in v2. The stack is intentionally flat — one process, one machine, no serverless orchestration.

### Static plan, not LLM-generated
Nova Micro outputs inconsistent plan format, so the plan node uses a hardcoded 5-step sequence (search → scrape ×2 → extract ×2). The evaluate node decides whether to loop back or synthesize.

### LangGraph agent loop
PLAN → EXECUTE → EVALUATE → SYNTHESIZE. MCP (Model Context Protocol) server decouples tools from the agent. Each tool wraps self-hosted or external clients with unified interfaces.

### Resilience per service
Every infrastructure client (SearXNG, Crawl4AI, Bedrock, ES, Redis) is wrapped with CircuitBreaker + Bulkhead + RetryWithBackoff + Timeout. Failures in one service don't cascade.

### SSE streaming over polling
Server-Sent Events stream agent progress and results in real time. The frontend receives incremental updates (plan → step results → final answer) on a single connection.

### Heuristic extraction as permanent fallback
Regex parser (prices in ₹/Rs/$/£/€, bedrooms 2BHK/Studio/Single, amenities AC/WiFi/Power Backup) runs when Bedrock is unavailable. Not a temporary workaround — it ships alongside the LLM extractor.

### Idempotent requests via Idempotency-Key
Redis-backed deduplication with 24h TTL. Same key returns cached result instead of re-running the agent. This prevents duplicate crawls on retries.

### PII stripped at extraction and output
Both the LLM extraction prompt and the final synthesized answer strip personally identifiable information. No phone numbers, emails, or names reach the user or Elasticsearch.

### Time-based ES indices for TTL
`properties-YYYY.MM.DD` indices let Elasticsearch delete expired data by dropping the index — simpler and cheaper than `_delete_by_query`.

### Images: original URLs only
Source image URLs are stored and passed through; no S3 rehosting, no CloudFront signing. Images load directly from the original listing page.

---

## Limitations

- **Static plan** — Nova Micro outputs inconsistent plan format; planning is hardcoded to 5 steps
- **Claude blocked** — must submit Anthropic use case form in AWS Bedrock console
- **Search quality** — SearXNG often returns category pages, not individual listings; post-filtering needed
- **SearXNG healthcheck** — Google rate-limits SearXNG health probes, but results still return via DuckDuckGo/Startpage
