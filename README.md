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

Each decision below explains **why** it was chosen (the problem it solves) and **how** it is implemented.

### Self-hosted by default

**Why:** Third-party search and scraping APIs (Brave Search, FireCrawl, SerpAPI) introduce recurring costs, rate limits, and external dependencies. A self-contained system that runs entirely with `docker-compose up` eliminates API keys, usage quotas, and network dependency on external providers.

**How:** SearXNG handles meta-search by aggregating DuckDuckGo, Startpage, and Wikipedia results via a single JSON API endpoint (`/search?format=json&q=...`). Crawl4AI runs a headless browser in a separate container, exposing a REST API (`http://crawl4ai:11235/crawl?url=...`) for page scraping. Both services are configured in `docker-compose.yml` and wired into the MCP tool layer as the default backends. The legacy Brave Search and FireCrawl clients remain in the codebase as optional fallbacks activated by setting `USE_BRAVE=1` or `USE_FIRECRAWL=1`.

### Single EC2 for everything

**Why:** A POC does not justify multi-service orchestration (ECS, Kubernetes, Lambda). Collocating all services on one machine eliminates network overhead between services, simplifies deployment to a single `docker compose up`, and keeps the infrastructure free-tier eligible.

**How:** Five Docker containers (FastAPI, Elasticsearch 8.x, Redis 7, SearXNG, Crawl4AI) share a `t3.micro` instance via a Docker bridge network. Service discovery uses container hostnames (e.g., `http://elasticsearch:9200`). Resource contention is managed by Docker's built-in CPU/memory limits set in `docker-compose.yml`. Single-point-of-failure risk is accepted — the system is designed for evaluation, not production SLAs.

### ES as only data store, not DynamoDB

**Why:** Accommodation listings are unstructured, short-lived (24h TTL), and need full-text search. DynamoDB adds secondary-index complexity for text search, requires managing a second storage system, and incurs per-request costs. Elasticsearch provides indexing, search, and storage in one system.

**How:** Daily time-based indices (`properties-YYYY.MM.DD`) partition data by ingestion date. The `repository.py` layer abstracts CRUD operations behind a `PropertyRepository` interface. TTL is enforced at the index level — a daily cron task or Elasticsearch ILM policy drops indices older than 1 day, which is exponentially cheaper and faster than `_delete_by_query` on individual documents.

### No DynamoDB, no API Gateway, no Lambda

**Why:** Serverless services add cold starts, IAM complexity, debugging difficulty, and cost unpredictability. A single FastAPI process with middleware handles routing, auth, rate limiting, and request validation — no API Gateway needed.

**How:** The entire API surface is a single FastAPI `FastAPI()` instance mounted on a root scope. AWS credentials are passed via environment variables or `~/.aws:/root/.aws:ro` volume mount. There is no Lambda handler, no API Gateway REST/V2 integration, and no SAM/CDK template. The deployment is pure Docker Compose.

### Static plan, not LLM-generated

**Why:** Amazon Nova Micro produces inconsistent JSON plan formats, making it unreliable as a planner. A hardcoded plan eliminates format-parsing errors, reduces latency (no LLM call for planning), and keeps the agent deterministic.

**How:** `plan.py` returns a fixed graph of 5 steps: `[search_web(count=8), scrape_url(index=0), scrape_url(index=1), extract_property(index=0), extract_property(index=1)]`. The `EVALUATE` node (`evaluate.py`) checks whether scraped URLs remain; if unprocessed results exist, it loops back to `EXECUTE`; otherwise it proceeds to `SYNTHESIZE`. This gives the agent some adaptability (it can choose to re-scrape or skip extraction) while keeping plan generation deterministic.

### LangGraph agent loop

**Why:** An agentic system needs a structured loop that plans, executes, evaluates results, and synthesizes answers. LangGraph provides a typed `StateGraph` with built-in state management, conditional edges, and configurable node execution — without building a custom state machine.

**How:** `graph.py` defines a `StateGraph` with `AgentState` (TypedDict) holding `plan`, `step_index`, `results`, `step_vars`, and `answer`. Four nodes — `plan_node`, `execute_node`, `evaluate_node`, `synthesize_node` — are connected via `add_edge` and `add_conditional_edges`. Each node reads and writes to `AgentState`. The MCP server (`FastMCP` with SSE transport) is embedded in the same FastAPI process, decoupling tool implementation from the agent graph. Tools are registered in `registry.py` and called by `execute_node` based on step names.

### Resilience per service

**Why:** In a multi-service architecture with network-dependent components (SearXNG, Crawl4AI, Bedrock, ES, Redis), any single failure can cascade and block the entire request. Each service needs independent fault isolation.

**How:** Every infrastructure client is wrapped with four resilience patterns:
- **CircuitBreaker** — trips after N consecutive failures (default 5), resets after a cooldown period (60s), prevents cascading calls to a dead service.
- **Bulkhead** — limits concurrent calls per service (e.g., 3 concurrent SearXNG requests) via a semaphore.
- **RetryWithBackoff** — retries up to 3 times with exponential backoff (base 1s, jitter 0.1×) for transient errors (timeouts, 429s, 503s).
- **Timeout** — per-service timeout via `asyncio.wait_for` (e.g., 15s for SearXNG, 60s for Bedrock).

These are composed as decorator-style wrappers in `src/infrastructure/resilience/`.

### SSE streaming over polling

**Why:** The agent loop takes 30-120 seconds to complete. Polling forces the frontend to repeatedly hit a status endpoint, increasing server load and adding latency between step transitions. SSE provides a single persistent connection with server-pushed updates.

**How:** The `/api/search` endpoint returns `StreamingResponse` with `text/event-stream` content type. The agent runs as a background asyncio task, publishing events to an `asyncio.Queue`. A separate streaming task reads from the queue and yields SSE-formatted lines (`data: {...}\n\n`). The frontend `useSearch.ts` hook opens an `EventSource` connection, parses `type`, `event`, and `done` events, and updates React state accordingly. Connection cleanup happens via `EventSource.close()` on unmount or request cancellation.

### Heuristic extraction as permanent fallback

**Why:** Bedrock Nova Micro can fail due to rate limits, model unavailability, or API errors. A crawling system must still produce results when the LLM is down. A regex-based extractor is deterministic, fast (milliseconds), and requires no external service.

**How:** `extraction.py` implements a two-phase extraction pipeline:
1. **LLM phase** — sends the raw markdown page content to Bedrock Nova Micro with a structured prompt requesting a JSON array of properties.
2. **Heuristic fallback** — if the LLM phase returns null, errors, or empty results, a regex parser scans the markdown for:
   - Prices: `₹\d+[,\d]*`, `Rs\d+`, `$\d+`, `£\d+`, `€\d+`
   - Bedroom types: `(\d+\s*(BHK|BHK|Bedroom|Bed|Room))|Studio|Single|Double`
   - Amenities: `AC|WiFi|Power Backup|Parking|Lift|Security`
   - Ratings: `(\d\.?\d*)\s*(?:/5|star|out of 5)`
   - Location & title: extracted from heading tags and geographic patterns
3. Both outputs are normalized to the same `Property` model schema.

### Idempotent requests via Idempotency-Key

**Why:** Network retries, browser double-clicks, and frontend reconnects can trigger duplicate agent runs. Without deduplication, each retry rescrapes the same websites and wastes Bedrock tokens.

**How:** The `IdempotentMiddleware` checks the `Idempotency-Key` header on every `POST /api/search` request. If the key exists in Redis with status `running`, the middleware returns the existing `search_id` and the client reconnects via SSE. If the key exists with status `completed`, the cached SSE events are replayed from Redis. Keys expire after 24h (configurable via `IDEMPOTENCY_TTL`). Redis storage uses the key format `idempotency:{key_hash}` with the SHA-256 hash of the key as the Redis key to prevent header size abuse.

### PII stripped at extraction and output

**Why:** Accommodation listings often contain phone numbers, email addresses, and owner names. Exposing PII violates privacy norms and creates liability. Stripping at both stages ensures no PII leaks even if one stage fails.

**How:** The LLM extraction prompt explicitly instructs the model to omit names, phone numbers, and email addresses from the output. A post-processing regex pass in `pii.py` removes remaining matches for:
- Phone numbers: `\+?\d{1,4}[-.\s]?\d{6,12}`, Indian mobile (`[6-9]\d{9}`), landline patterns
- Emails: `[\w.+-]+@[\w-]+\.[\w.]+`
- Names: triggers on `contact`, `call`, `owner`, `landlord` keywords in surrounding context

The same filter runs on the final synthesized answer before it reaches the SSE stream.

### Time-based ES indices for TTL

**Why:** Compliance and storage management require automatic data expiration. `_delete_by_query` is slow (scroll-based, one doc at a time) and competes with search traffic. Dropping an entire index is an O(1) filesystem operation.

**How:** `repository.py` builds the index name from the current UTC date: `properties-{datetime.utcnow().strftime('%Y.%m.%d')}`. Each day's data goes into a new index. A lightweight cleanup coroutine in the FastAPI lifespan runs every hour — it lists indices matching `properties-*`, drops any older than 48h, and logs the result. The `template` index template enforces a uniform mapping across all daily indices.

### Images: original URLs only

**Why:** Rehosting listing images on S3 multiplies storage costs, requires presigned URL generation, and creates copyright ambiguity. Users click through to the original listing anyway.

**How:** The extraction pipeline extracts `src` attributes from `<img>` tags and stores the absolute URLs as-is in the `Property.images` field. The frontend renders them directly in `<img src={url} />` tags with `loading="lazy"`. No download, upload, or signing step exists anywhere in the pipeline.

---

## Limitations

- **Static plan** — Nova Micro outputs inconsistent plan format; planning is hardcoded to 5 steps
- **Claude blocked** — must submit Anthropic use case form in AWS Bedrock console
- **Search quality** — SearXNG often returns category pages, not individual listings; post-filtering needed
- **SearXNG healthcheck** — Google rate-limits SearXNG health probes, but results still return via DuckDuckGo/Startpage
