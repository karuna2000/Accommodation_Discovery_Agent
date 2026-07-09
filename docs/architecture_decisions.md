# Architecture Decision Records

Each decision explains **why** it was chosen (the problem it solves) and **how** it is implemented.

---

## 1. Self-hosted by default

**Why:** Third-party search and scraping APIs (Brave Search, FireCrawl, SerpAPI) introduce recurring costs, rate limits, and external dependencies. A self-contained system that runs entirely with `docker-compose up` eliminates API keys, usage quotas, and network dependency on external providers.

**How:** SearXNG handles meta-search by aggregating DuckDuckGo, Startpage, and Wikipedia results via a single JSON API endpoint (`/search?format=json&q=...`). Crawl4AI runs a headless browser in a separate container, exposing a REST API (`http://crawl4ai:11235/crawl?url=...`) for page scraping. Both services are configured in `docker-compose.yml` and wired into the MCP tool layer as the default backends. The legacy Brave Search and FireCrawl clients remain in the codebase as optional fallbacks, activated by setting `BRAVE_API_KEY` or `FIRECRAWL_API_KEY`.

---

## 2. Single EC2 for everything

**Why:** A POC does not justify multi-service orchestration (ECS, Kubernetes, Lambda). Collocating all services on one machine eliminates network overhead between services, simplifies deployment to a single `docker compose up`, and keeps the infrastructure free-tier eligible.

**How:** Five Docker containers (FastAPI, Elasticsearch 8.x, Redis 7, SearXNG, Crawl4AI) share a `t3.micro` instance via a Docker bridge network. Service discovery uses container hostnames (e.g., `http://elasticsearch:9200`). Resource contention is managed by Docker's built-in CPU/memory limits set in `docker-compose.yml`. Single-point-of-failure risk is accepted — the system is designed for evaluation, not production SLAs.

---

## 3. ES as only data store, not DynamoDB

**Why:** Accommodation listings are unstructured, short-lived (24h TTL), and need full-text search. DynamoDB adds secondary-index complexity for text search, requires managing a second storage system, and incurs per-request costs. Elasticsearch provides indexing, search, and storage in one system.

**How:** Daily time-based indices (`properties-YYYY.MM.DD`) partition data by ingestion date. The `repository.py` layer abstracts CRUD operations behind a `PropertyRepository` interface. TTL is enforced at the index level — a daily cron task or Elasticsearch ILM policy drops indices older than 1 day, which is exponentially cheaper and faster than `_delete_by_query` on individual documents.

---

## 4. No DynamoDB, no API Gateway, no Lambda

**Why:** Serverless services add cold starts, IAM complexity, debugging difficulty, and cost unpredictability. A single FastAPI process with middleware handles routing, auth, rate limiting, and request validation — no API Gateway needed.

**How:** The entire API surface is a single FastAPI `FastAPI()` instance mounted on a root scope. AWS credentials are passed via environment variables or `~/.aws:/root/.aws:ro` volume mount. There is no Lambda handler, no API Gateway REST/V2 integration, and no SAM/CDK template. The deployment is pure Docker Compose.

---

## 5. Static plan, not LLM-generated

**Why:** Amazon Nova Micro produces inconsistent JSON plan formats, making it unreliable as a planner. A hardcoded plan template eliminates format-parsing errors, reduces latency (no LLM call for planning), and keeps the agent deterministic.

**How:** `plan.py` generates a plan dynamically based on intent specificity and constraint tier. For a highly specific query (4+ fields), it generates 5 steps; for a generic query, up to 25 steps. The `EVALUATE` node checks whether scraped URLs remain; if no results were found, it increments the constraint tier (up to 4 levels of progressive relaxation) and re-plans with broader search parameters.

---

## 6. LangGraph agent loop

**Why:** An agentic system needs a structured loop that plans, executes, evaluates results, and synthesizes answers. LangGraph provides a typed `StateGraph` with built-in state management, conditional edges, and configurable node execution — without building a custom state machine.

**How:** `graph.py` defines a `StateGraph` with `AgentState` (TypedDict) holding `plan`, `step_index`, `results`, `step_vars`, and `answer`. Six nodes — `intent_node`, `plan_node`, `execute_node`, `evaluate_node`, `validate_node`, `synthesize_node` — are connected via `add_edge` and `add_conditional_edges`. Each node reads and writes to `AgentState`. The MCP server (`FastMCP` with SSE transport) is embedded in the same FastAPI process, decoupling tool implementation from the agent graph. Tools are registered in `registry.py` and called by `execute_node` based on step names.

---

## 7. Resilience per service

**Why:** In a multi-service architecture with network-dependent components (SearXNG, Crawl4AI, Bedrock, ES, Redis), any single failure can cascade and block the entire request. Each service needs independent fault isolation.

**How:** Every infrastructure client is wrapped with four resilience patterns:
- **CircuitBreaker** — trips after N consecutive failures (default 5), resets after a cooldown period (60s), prevents cascading calls to a dead service.
- **Bulkhead** — limits concurrent calls per service (e.g., 3 concurrent SearXNG requests) via a semaphore.
- **RetryWithBackoff** — retries up to 3 times with exponential backoff (base 1s, jitter 0.1×) for transient errors (timeouts, 429s, 503s).
- **Timeout** — per-service timeout via `asyncio.wait_for` (e.g., 15s for SearXNG, 60s for Bedrock).

These are composed as decorator-style wrappers in `src/infrastructure/resilience/`.

---

## 8. SSE streaming over polling

**Why:** The agent loop takes 30-120 seconds to complete. Polling forces the frontend to repeatedly hit a status endpoint, increasing server load and adding latency between step transitions. SSE provides a single persistent connection with server-pushed updates.

**How:** The `/api/search` endpoint returns `StreamingResponse` with `text/event-stream` content type. The agent graph streams events via `graph.astream()`, which yields node outputs as they complete. The search route handler wraps these events in SSE-formatted lines (`data: {...}\n\n`). The frontend `useSearch.ts` hook opens an `EventSource` connection, parses `type`, `event`, and `done` events, and updates React state accordingly. Connection cleanup happens via `EventSource.close()` on unmount or request cancellation.

---

## 9. Heuristic extraction as permanent fallback

**Why:** Bedrock Nova Micro can fail due to rate limits, model unavailability, or API errors. A crawling system must still produce results when the LLM is down. A regex-based extractor is deterministic, fast (milliseconds), and requires no external service.

**How:** `extraction.py` implements a two-phase extraction pipeline:
1. **LLM phase** — sends the raw markdown page content to Bedrock Nova Micro with a structured prompt requesting a JSON array of properties.
2. **Heuristic fallback** — if the LLM phase returns null, errors, or empty results, a regex parser scans the markdown for:
   - Prices: `₹\d+[,\d]*`, `Rs\d+`, `$\d+`, `£\d+`, `€\d+`
   - Bedroom types: `(\d+\s*(BHK|Bedroom|Bed|Room))|Studio|Single|Double`
   - Amenities: `AC|WiFi|Power Backup|Parking|Lift|Security`
   - Ratings: `(\d\.?\d*)\s*(?:/5|star|out of 5)`
   - Location & title: extracted from heading tags and geographic patterns
3. Both outputs are normalized to the same `CrawledProperty` model schema.

---

## 10. Idempotent requests via Idempotency-Key

**Why:** Network retries, browser double-clicks, and frontend reconnects can trigger duplicate agent runs. Without deduplication, each retry rescrapes the same websites and wastes Bedrock tokens.

**How:** The search route handler checks the `Idempotency-Key` header on every `POST /api/search` request. If the key exists in Redis with an in-progress status, a `409 Conflict` is returned. If the key exists with a `completed` status, the cached response is returned directly. Keys expire after 24h (configurable via `IDEMPOTENCY_TTL`). Redis storage uses the key directly via the `IdempotencyRepository`.

---

## 11. PII stripped at extraction and output

**Why:** Accommodation listings often contain phone numbers, email addresses, and personal identifiers. Exposing PII violates privacy norms and creates liability. Stripping at both stages ensures no PII leaks even if one stage fails.

**How:** The LLM extraction prompt explicitly instructs the model to omit personal information from the output. A post-processing regex pass in `pii.py` removes remaining matches for:
- Phone numbers: `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b`
- Emails: `\b[\w.+-]+@[\w-]+\.[\w.-]+\b`
- SSNs: `\b\d{3}-\d{2}-\d{4}\b`
- Credit card numbers: `\b(?:\d[ -]*?){13,16}\b`

The same filter runs on the final synthesized answer before it reaches the SSE stream.

---

## 12. Time-based ES indices for TTL

**Why:** Compliance and storage management require automatic data expiration. `_delete_by_query` is slow (scroll-based, one doc at a time) and competes with search traffic. Dropping an entire index is an O(1) filesystem operation.

**How:** `repository.py` builds the index name from the current UTC date: `properties-{datetime.utcnow().strftime('%Y.%m.%d')}`. Each day's data goes into a new index. A cleanup method (`delete_old_indices`) lists indices matching `properties-*` and drops any older than the configured retention period.

---

## 13. Images: original URLs only

**Why:** Rehosting listing images on S3 multiplies storage costs, requires presigned URL generation, and creates copyright ambiguity. Users click through to the original listing anyway.

**How:** The extraction pipeline extracts `src` attributes from `<img>` tags and stores the absolute URLs as-is in the `CrawledProperty.images` field. The frontend renders them directly in `<img src={url} />` tags with `loading="lazy"`. No download, upload, or signing step exists anywhere in the pipeline.
