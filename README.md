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
INTENT ──► PLAN ──► EXECUTE ──► EVALUATE ──► VALIDATE ──► SYNTHESIZE ──► DONE
                       │              │
                       └── (loop) ────┘
                              │
                    (no results? relax constraints & re-plan)
```

1. **INTENT** — Classifies query, extracts budget/location/BHK/amenities via Bedrock or regex fallback. Detects greetings, off-topic queries, and asks for clarification when key info (e.g., location) is missing.
2. **PLAN** — Generates a search plan scaled by intent specificity: specific queries (4+ fields) → 5 steps; vague queries → up to 25 steps. On retry, progressively relaxes constraints across 4 tiers (drop budget → drop property type → broaden location).
3. **EXECUTE** — Runs each step via MCP tools (`search_web`, `scrape_url`, `extract_property`). Resolves `$variable` references between steps. Filters URLs by accommodation relevance and filters extracted properties by query constraints.
4. **EVALUATE** — Decides: continue executing → loop to EXECUTE; no results → re-plan with relaxed constraints (up to 4 tiers); all done → proceed to VALIDATE.
5. **VALIDATE** — Strips PII from results, scores property completeness, filters out irrelevant/low-confidence listings. Uses LLM validation when available, regex fallback otherwise.
6. **SYNTHESIZE** — Generates conversational answer from validated properties. Shows match reasons (✓ under budget, ✓ correct bedrooms, ✓ in requested area). Falls back to formatted text when Bedrock is unavailable.

---

## Features

- **Conversational search** — natural language queries for accommodation
- **Self-hosted infrastructure** — SearXNG (meta-search) + Crawl4AI (web scraping) in Docker
- **LLM-powered extraction** — Amazon Bedrock Nova Micro extracts structured property data from raw pages
- **Heuristic fallback** — regex-based property extractor when Bedrock is unavailable
- **Intent classification** — extracts budget, BHK, location, gender, amenities; asks for clarification on vague queries
- **Constraint relaxation** — 4-tier progressive broadening when no results found
- **Resilience stack** — per-service circuit breakers, bulkheads, timeouts, retry with exponential backoff + jitter
- **Idempotent requests** — Redis-backed `Idempotency-Key` header (24h TTL)
- **SSE streaming** — real-time agent progress and results via Server-Sent Events
- **Request cancellation** — `POST /api/search/{id}/cancel`
- **PII stripping** — emails, phones, SSNs, CC numbers removed at extraction and output
- **Data expiration** — time-based Elasticsearch indices (`properties-YYYY.MM.DD`)
- **Grounding check** — validates synthesized answer against extracted data
- **Input guardrails** — query validation, HTML sanitization, blocked terms, rate limiting

---

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for frontend development)
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
BEDROCK_FALLBACK_MODEL_ID=us.amazon.nova-micro-v1:0
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
data: {"type": "event", "data": {"intent": {"intent": {...}, "needs_clarification": false}}}
data: {"type": "event", "data": {"plan": {"plan": "1. search_web(...)\n2. scrape_url(...)"}}}
data: {"type": "event", "data": {"execute": {"step_index": 1, "results": [...]}}}
data: {"type": "done", "search_id": "...", "answer": "Here are some properties..."}
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check (ES + Redis status) |
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
│   │       ├── health.py       # GET /api/health
│   │       └── search.py       # SSE streaming, cancel, status
│   ├── agent/
│   │   ├── graph.py            # LangGraph StateGraph (6-node agent loop)
│   │   ├── state.py            # AgentState TypedDict
│   │   └── nodes/
│   │       ├── intent.py       # Intent classification + clarification
│   │       ├── plan.py         # Dynamic plan generation (scaled by specificity)
│   │       ├── execute.py      # Tool execution + $variable resolution
│   │       ├── evaluate.py     # Loop decision + constraint relaxation
│   │       ├── validate.py     # Output validation + PII stripping
│   │       └── synthesize.py   # Bedrock answer generation + fallback
│   ├── mcp/
│   │   ├── server.py           # FastMCP server (SSE transport)
│   │   ├── registry.py         # Tool registry (@tool decorator)
│   │   └── tools/
│   │       ├── base.py         # Base tool + ToolDependencies
│   │       ├── brave_search.py # search_web (SearXNG → Brave fallback)
│   │       ├── firecrawl.py    # scrape_url (Crawl4AI → FireCrawl fallback)
│   │       ├── extraction.py   # extract_property (Bedrock + heuristic regex)
│   │       ├── es.py           # search_es + store_property
│   │       ├── cache.py        # search_cache + store_cache
│   │       └── synthesize.py   # synthesize_answer
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
│   │   └── output/             # PII stripping, grounding checks, completeness
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
├── tests/                      # 153 tests (pytest, async)
│
└── docs/
    └── architecture_decisions.md  # Detailed ADRs (why + how)
```

---

## Configuration

All settings via environment variables (`.env` or `docker-compose` env):

### Core
| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_PROFILE` | `""` | AWS profile name |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-micro-v1:0` | Primary LLM |
| `BEDROCK_FALLBACK_MODEL_ID` | `us.anthropic.claude-3-haiku-20240307-v1:0` | Fallback LLM (⚠️ Claude blocked — set to Nova Micro) |
| `BEDROCK_EMBEDDING_MODEL_ID` | `us.cohere.embed-v4:0` | Embedding model |

### Infrastructure
| Variable | Default | Description |
|----------|---------|-------------|
| `ES_HOST` | `elasticsearch` | Elasticsearch host |
| `ES_PORT` | `9200` | Elasticsearch port |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `SEARXNG_HOST` | `searxng` | SearXNG host |
| `SEARXNG_PORT` | `8080` | SearXNG port |
| `CRAWL4AI_HOST` | `crawl4ai` | Crawl4AI host |
| `CRAWL4AI_PORT` | `11235` | Crawl4AI port |
| `CRAWL4AI_API_TOKEN` | `crawl4ai-local-token` | Crawl4AI auth token |

### Resilience
| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_TIMEOUT` | `60.0` | Bedrock request timeout (s) |
| `SEARXNG_TIMEOUT` | `15.0` | SearXNG request timeout |
| `CRAWL4AI_TIMEOUT` | `60.0` | Crawl4AI request timeout |
| `SEARXNG_MAX_CONCURRENT` | `3` | Max concurrent SearXNG requests |
| `CRAWL4AI_MAX_CONCURRENT` | `2` | Max concurrent Crawl4AI requests |
| `BEDROCK_MAX_CONCURRENT` | `1` | Max concurrent Bedrock requests |

### Optional fallback APIs
| Variable | Default | Description |
|----------|---------|-------------|
| `BRAVE_API_KEY` | `""` | Set to activate Brave Search as fallback for SearXNG |
| `FIRECRAWL_API_KEY` | `""` | Set to activate FireCrawl as fallback for Crawl4AI |

Full list in `src/config/settings.py`.

---

## Testing

```bash
# All tests (153 passing)
make test

# Or directly
docker compose run --rm api pytest -v

# Local (without Docker)
source .venv/bin/activate
pytest -v

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

CI/CD via GitHub Actions (`.github/workflows/deploy-oidc.yml`): runs tests → builds Docker image → pushes to ECR → deploys to EC2 via SSH.

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

Key design decisions with one-line summaries. Full rationale in [`docs/architecture_decisions.md`](docs/architecture_decisions.md).

| Decision | Summary |
|----------|---------|
| Self-hosted by default | SearXNG + Crawl4AI replace third-party APIs — no API keys, no rate limits |
| Single EC2 | All 5 Docker containers on one t3.micro — simple, free-tier eligible |
| ES as only data store | Full-text search + storage in one system; no DynamoDB |
| No API Gateway / Lambda | FastAPI handles routing, auth, rate limiting directly |
| Static plan template | Nova Micro outputs unreliable plan JSON; plan is code-generated, not LLM-generated |
| LangGraph agent loop | 6-node StateGraph with typed state and conditional edges |
| Resilience per service | CircuitBreaker + Bulkhead + Retry + Timeout on every external call |
| SSE streaming | Server-pushed events over a single connection; no polling |
| Heuristic extraction fallback | 15+ regex patterns as permanent fallback when Bedrock is unavailable |
| Idempotent requests | `Idempotency-Key` header, Redis-backed, 24h TTL |
| PII stripping | Regex removes emails, phones, SSNs, CC numbers at extraction and output |
| Time-based ES indices | `properties-YYYY.MM.DD` for O(1) TTL enforcement |
| Images: original URLs | No S3 rehosting — reference source URLs directly |

---

## Limitations

- **Static plan** — Nova Micro outputs inconsistent plan format; planning is code-generated, not LLM-generated
- **Claude blocked** — must submit Anthropic use case form in AWS Bedrock console
- **Search quality** — SearXNG often returns category pages, not individual listings; post-filtering needed
- **SearXNG healthcheck** — Google rate-limits SearXNG health probes, but results still return via DuckDuckGo/Startpage
