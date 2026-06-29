# Accommodation Discovery Agent — Project Context

## Goal
Build an AI-powered accommodation discovery platform that crawls listings from the web, extracts structured property data, caches it in Elasticsearch, and serves conversational search results via an agentic LLM loop with self-hosted search and scraping infrastructure.

## Constraints & Preferences
- Pure crawl-based architecture: no owner ingestion, no DynamoDB, no student accounts, no booking flow
- Agentic solution using LangGraph for plan–execute–evaluate loops, with MCP server for tool decoupling
- All services on a single EC2 t3.micro: FastAPI, Elasticsearch 8.x, Redis, SearXNG, Crawl4AI, all in docker-compose
- Self-hosted by default: SearXNG replaces Brave Search; Crawl4AI replaces FireCrawl API
- Bedrock for LLM + embeddings — Claude models blocked (need Anthropic use case form); Amazon Nova Micro (`us.amazon.nova-micro-v1:0`) and Cohere Embed v4 (`us.cohere.embed-v4:0`) work immediately
- Plan is static (5-step hardcoded, not LLM-generated): Nova outputs unreliable plan format
- Requests idempotent via `Idempotency-Key` header (Redis-backed, 24h TTL)
- Per-service circuit breakers, timeouts, retry with exponential backoff + jitter, bulkhead semaphores
- Images: reference original source URLs, do NOT rehost on S3
- PII stripped at extraction and output; data expires from ES after 24h via time-based indices
- Cost tracking via Redis daily counters; request cancellation via `POST /api/search/{id}/cancel`
- Frontend: React on S3 + CloudFront; API proxied through CloudFront → EC2 (no API Gateway, no Lambda)

## Progress
### Done
- All planning documents created (`ideaAndplan/`): idea.md, architecture_decision.md, dev_plan.md, final_plan.md, tech_stack.md, low_level_design.md, aws_services.md
- Stage 1–6 complete: FastAPI app, docker-compose (ES + Redis + SearXNG + Crawl4AI + API), MCP server with 7 tools plus Bedrock Nova Micro support, all infrastructure clients with resilience stack, Elasticsearch + Redis persistence, LangGraph agent (PLAN → EXECUTE → EVALUATE → SYNTHESIZE), guardrails, SSE streaming API, React frontend (Vite + Tailwind v4)
- **Bedrock Nova Micro working end-to-end**: Full flow tested — SearXNG returns real URLs → Crawl4AI scrapes pages → Nova Micro extracts structured data via calls + synthesizes conversational response → SSE delivers answer. Found real properties (Krishan Kunj PG, 2 BHK in Mansarovar Extension). `"error": null`.
- **Self-hosted search/scraping**: SearXNG (DuckDuckGo, Startpage, Wikipedia engines) replaces Brave Search. Crawl4AI replaces FireCrawl. Both configured in docker-compose, wired into tool dependencies.
- **Heuristic property extractor**: Regex parser (prices in ₹/Rs/$/£/€, bedrooms 2BHK/Studio/Single, amenities AC/WiFi/Power Backup, titles, tags, location, images, rating) as permanent fallback when Bedrock unavailable.
- **Static plan (no Bedrock planning)**: Plan node now hardcodes a 5-step plan (search_web count=8 → scrape 2 URLs → extract 2). Nova Micro outputs inconsistent plan format, so LLM planning is disabled.
- **Multi-format Bedrock client**: Handles both Claude (anthropic_version) and Nova (messages.content[].text + inferenceConfig) formats. Handles both Titan (inputText) and Cohere (texts[] + input_type) embedding formats. Inference profile IDs (`us.amazon.nova-micro-v1:0`, `us.cohere.embed-v4:0`).
- **AWS credentials**: Supports direct keys via `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` or profile via `AWS_PROFILE` with `~/.aws:/root/.aws:ro` mount. `aioboto3` dependency.
- **86/86 tests passing**, 0 ruff errors, frontend builds with 0 TS errors.

### Next Steps
1. Submit Anthropic use case form in AWS Bedrock console to unblock Claude models (for better reasoning in extraction)
2. Improve search result quality: SearXNG returns generic category pages, not individual listing URLs — refine query or post-filter
3. Improve heuristic extractor for multi-listing category pages (split on listing boundaries)
4. Stage 7: Deploy to EC2 with docker-compose, configure CloudFront + Route53

### Blocked
- Claude models blocked — all Anthropic models fail with `ResourceNotFoundException: Model use case details have not been submitted`. User must fill out Anthropic use case form in AWS Bedrock console.
- SearXNG shows `unhealthy` in Docker healthcheck (Google rate-limits), but returns results from DuckDuckGo, Startpage, Wikipedia.

## Key Decisions
- Self-hosted search/scraping by default: SearXNG + Crawl4AI replace Brave Search and FireCrawl
- LangGraph agent with MCP tool layer; FastMCP with SSE transport embedded in same FastAPI process
- All infrastructure clients wrapped with CircuitBreaker + Bulkhead + RetryWithBackoff + Timeout
- **Nova Micro as primary LLM** ($0.035/1M tokens), Cohere Embed v4 for vectors. Both primary and fallback set to same Nova model to avoid Claude form error. Switch to Claude models once form is approved.
- **Static plan** — Nova Micro generates unreliable plan format; plan_node uses hardcoded 5-step plan
- Time-based ES indices (`properties-YYYY.MM.DD`) for TTL enforcement
- SSE streaming for POST /api/search with Idempotency-Key deduplication
- `step_vars` in AgentState stores named variables (`result_url_1`, `url_1`, `markdown_2`, `result_url_1_2`) for cross-step `$variable` resolution
- Heuristic extraction as permanent fallback when Bedrock unavailable

## Branch Structure
- `main` — Stage 1 scaffold
- `stage/05-agent-orchestrator` — Stages 1–6 plus self-hosted infra, heuristic fallbacks, Nova Micro support

## Relevant Code Locations
- `src/agent/graph.py` — build_agent(), run_agent(), StateGraph with PLAN/EXECUTE/EVALUATE/SYNTHESIZE
- `src/agent/state.py` — AgentState TypedDict
- `src/agent/nodes/plan.py` — Static 5-step plan (no Bedrock)
- `src/agent/nodes/execute.py` — Step execution, variable resolution ($markdown_N, $result_url_N)
- `src/agent/nodes/synthesize.py` — synthesize_node with Bedrock + fallback formatting
- `src/infrastructure/external/bedrock.py` — BedrockClient: Claude + Nova formats, Cohere embeddings, `_strip_code_blocks()`
- `src/infrastructure/external/searxng.py` — SearXNG client (replaces Brave Search)
- `src/infrastructure/external/crawl4ai.py` — Crawl4AI client (replaces FireCrawl)
- `src/mcp/tools/extraction.py` — ExtractionTool with Bedrock + heuristic regex fallback
- `src/mcp/tools/synthesize.py` — SynthesizeTool with Bedrock + fallback formatting
- `src/api/server.py` — FastAPI app factory, mounts MCP server, AWS env vars
- `src/api/routes/search.py` — SSE streaming endpoint
- `tests/` — 86 tests, all passing
- `frontend/` — React 18 + Tailwind v4 chat UI
- `docker-compose.yml` — 5 services: elasticsearch, redis, searxng, crawl4ai, api (mounts `~/.aws:/root/.aws:ro`)
