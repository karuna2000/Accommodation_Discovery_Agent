# Accommodation Discovery Agent — Project Context

## Goal
Build an AI-powered accommodation discovery platform that crawls listings from the web, extracts structured property data, caches it in Elasticsearch, and serves conversational search results via an agentic LLM loop.

## Constraints & Preferences
- Pure crawl-based architecture: no owner ingestion, no DynamoDB, no student accounts, no booking flow
- Agentic solution using LangGraph for plan–execute–evaluate loops, with MCP server for tool decoupling
- All services run on a single EC2 t3.micro (free tier): FastAPI, Elasticsearch 8.x, Redis, all in docker-compose
- FireCrawl API (not Playwright) for JS-rendered page scraping; Brave Search API for URL discovery; Bedrock Claude 3 Sonnet + Haiku fallback for LLM; Titan Embeddings v2 for vectors
- Requests must be idempotent via `Idempotency-Key` header (Redis-backed, 24h TTL)
- Per-service circuit breakers, timeouts, retry with exponential backoff + jitter, bulkhead semaphores
- Images: reference original source URLs, do NOT rehost on S3 (copyright compliance)
- PII stripped at extraction and output; data expires from ES after 24h via time-based indices
- Cost tracking via Redis daily counters; request cancellation via `POST /api/search/{id}/cancel`
- Frontend: React on S3 + CloudFront; API proxied through CloudFront → EC2 (no API Gateway, no Lambda)

## Progress
### Done
- All planning documents created (`ideaAndplan/`): idea.md, architecture_decision.md, dev_plan.md, final_plan.md, tech_stack.md, low_level_design.md, aws_services.md
- Stage 1 (Project Scaffold): FastAPI app factory, Settings/Pydantic config, docker-compose with ES+Redis+FastAPI, Makefile, health endpoint, error hierarchy, full directory structure matching LLD
- Stage 2 (MCP Server): domain models (CrawledProperty, CrawlJob, SearchQuery), BaseTool ABC with ToolDependencies, ToolRegistry with `@tool` decorator, FastMCP server, 7 stub MCP tools, all `__init__.py` wired
- Stage 3 (Web Tools with Resilience): CircuitBreaker (3-state), RetryWithBackoff (exponential + jitter), Timeout (asyncio.wait_for), Bulkhead (asyncio.Semaphore), Brave Search API client, FireCrawl API client, Bedrock client (Sonnet → Haiku fallback, Titan Embeddings v2, `extract_property` + `synthesize`), all wrapped with resilience stack (Bulkhead → CB → Retry → Timeout), wired into server lifespan
- Stage 4 (Elasticsearch + Redis Persistence): `CrawledPropertyESRepository` with time-based indices (`properties-YYYY.MM.DD`), strict mapping (geo_point, dense_vector 1024d, hybrid multi-field search), `CacheRepository` (cosine similarity cache with optional auto-embedding), `JobRepository` (CrawlJob CRUD), `IdempotencyRepository` (SETNX acquire/release), all wired into ToolDependencies
- Stage 5 (Agent Orchestrator + Guardrails + API): LangGraph agent (PLAN → EXECUTE → EVALUATE → SYNTHESIZE), `AgentState` TypedDict with `decision` routing, context injected via `RunnableConfig`, input guardrails (intent classifier, content filter, sliding window rate limiter), output guardrails (PII stripper for email/phone/SSN/CC, grounding checker), `POST /api/search` SSE streaming endpoint with idempotency + caching + job tracking, `GET /api/search/{id}`, `POST /api/search/{id}/cancel`
- Stage 6 (React Frontend): Vite + React 18 + TypeScript strict + Tailwind CSS v4, chat-style UI with SSE streaming, cancel/clear buttons, Vite proxy to FastAPI backend

### Next Steps
1. Stage 7: Deploy to EC2 with docker-compose, configure CloudFront + Route53

### Blocked
- No production API keys configured: `BRAVE_API_KEY`, `FIRECRAWL_API_KEY` are empty in `.env`; all external clients fall through to stub/mock behavior gracefully

## Key Decisions
- LangGraph agent orchestrator with MCP tool layer: LangGraph manages state (plan → execute → evaluate → synthesize), MCP provides decoupled, pluggable tool definitions
- FastMCP with SSE transport, embedded in same FastAPI process: single deployable, no separate MCP server process
- All infrastructure clients wrapped with CircuitBreaker + Bulkhead + RetryWithBackoff + Timeout: one consistent failure pattern per external service
- Fallback LLM chain: Claude Sonnet → Claude Haiku (Sonnet for reasoning, Haiku for cheaper fallback)
- Time-based ES indices (`properties-YYYY.MM.DD`): simpler TTL enforcement than delete_by_query
- Agent routing fixed by including `decision` in `AgentState` TypedDict — LangGraph silently dropped keys not in the schema, causing infinite loops
- SSE streaming for POST /api/search: allows real-time progress updates while the agent runs; `Idempotency-Key` deduplication prevents duplicate processing

## Branch Structure
- `main` — Stage 1 scaffold
- `stage/02-mcp-server` — Stage 2 (MCP domain models, tools, server)
- `stage/03-web-tools` — Stage 3 (resilience, Brave, FireCrawl, Bedrock clients)
- `stage/04-es-redis` — Stage 4 (ES + Redis persistence)
- `stage/05-agent-orchestrator` — Stages 5 + 6 (agent, guardrails, search API, React frontend)

Each branch is merged forward (e.g. `stage/03-web-tools` contains Stages 1–3).

## Relevant Code Locations
- `src/agent/graph.py` — build_agent(), run_agent(), StateGraph with PLAN/EXECUTE/EVALUATE/SYNTHESIZE
- `src/agent/state.py` — AgentState TypedDict
- `src/agent/nodes/` — plan_node, execute_node, evaluate_node, synthesize_node
- `src/guardrails/input/classifier.py` — intent classification + content filter
- `src/guardrails/input/rate_limiter.py` — sliding window rate limiter
- `src/guardrails/output/pii.py` — PII stripping
- `src/guardrails/output/grounding.py` — grounding checker
- `src/api/routes/search.py` — POST /api/search (SSE), GET /api/search/{id}, POST /api/search/{id}/cancel
- `src/api/server.py` — FastAPI app factory, mounts MCP server, includes routers
- `tests/test_agent_graph.py`, `tests/test_agent_nodes.py`, `tests/test_guardrails.py` — 87 tests total, all passing
- `frontend/src/hooks/useSearch.ts` — SSE stream reader, cancel, idempotency key generation
- `frontend/src/components/Chat.tsx` — Chat container, message list, input form, cancel/clear buttons
- `frontend/vite.config.ts` — Vite dev server with `/api` proxy to `localhost:8000`
