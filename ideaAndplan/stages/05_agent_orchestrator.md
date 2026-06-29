# Stage 5: Agent Orchestrator + Guardrails + API

**Goal:** LangGraph agent with PLAN→EXECUTE→EVALUATE→SYNTHESIZE loop, guardrails, and the main search API endpoint.

---

## Agent Architecture

### State Machine (LangGraph)

```
                    ┌─────────┐
                    │  PLAN   │  LLM generates search plan
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │ EXECUTE │  Runs one tool call per step
                    └────┬────┘
                         │
                    ┌────▼─────┐
                    │ EVALUATE │  Checks if results are sufficient
                    └────┬─────┘
                   ┌─────┴──────┐
                   │            │
              ┌────▼───┐   ┌───▼────────┐
              │ PLAN   │   │ SYNTHESIZE │  LLM generates answer
              │ (loop) │   └───┬────────┘
              └────────┘       │
                         ┌─────▼─────┐
                         │   DONE    │
                         └───────────┘
```

### AgentState

```python
class AgentState(TypedDict):
    query: str
    plan: str  # LLM-generated multi-step plan
    step_index: int
    max_steps: int
    results: list[dict]  # accumulated CrawledProperties as dicts
    synthesized_answer: str | None
    error: str | None
    iteration: int
```

### Plan Node

Input: `query`
Output: `plan` (a multi-line string like:
```
1. search_web("studio near UCLA")
2. scrape_url(result_url)
3. extract_property(markdown)
...
```
)
The LLM reads the available tool schemas from `ToolRegistry.get_schemas()` and generates a concrete plan.

### Execute Node

Input: `plan`, `step_index`
Action: Parses the plan line at `step_index`, extracts the tool name and arguments, calls `tool_dict[name].run(**args)`, appends result to `results`.
Increments `step_index`.

### Evaluate Node

Input: `results`, `query`, `plan`, `step_index`
Checks:
- If all plan steps are executed → route to SYNTHESIZE
- If results contain enough properties → route to SYNTHESIZE
- If iteration > max_iterations → route to SYNTHESIZE (with error)
- Otherwise → route to PLAN for refinement

### Synthesize Node

Input: `query`, `results`
Uses `BedrockClient.synthesize()` or the `synthesize_answer` MCP tool to generate a conversational response.
Sets `synthesized_answer` → routes to END.

---

## Guardrails

### Input Guardrails

**Intent Classifier:** Checks if the query is about accommodation search. Non-accommodation queries (e.g., "what is the weather") are blocked with `QueryBlockedError`.

**Content Filter:** Checks for toxic, harmful, or inappropriate content. Blocks with `QueryBlockedError`.

**Rate Limiter:** Sliding window counter. Keyed by IP + user ID. Blocks with `RateLimitError` after `rate_limit_per_minute` requests.

### Output Guardrails

**PII Stripper:** Removes emails, phone numbers, SSNs, credit card numbers from the synthesized answer before returning to the user.

**Grounding Check:** Verifies that claims in the synthesized answer are supported by the crawled properties. If a claim is ungrounded, re-synthesizes with stricter instructions.

---

## API Endpoint

### POST /api/search

```json
// Request
POST /api/search
Idempotency-Key: <uuid>
Content-Type: application/json
{
  "query": "studio near UCLA under $1500",
  "max_iterations": 5,
  "location_hint": "Los Angeles"
}

// Response (SSE stream)
data: {"type": "plan", "content": "1. search_web..."}
data: {"type": "progress", "step": 1, "tool": "search_web", "result": [...]}
data: {"type": "progress", "step": 2, "tool": "scrape_url", "result": "..."}
data: {"type": "synthesis", "content": "I found 3 studios..."}
data: {"type": "done", "search_id": "..."}
```

The endpoint:
1. Checks `Idempotency-Key` → returns cached response if already completed
2. Runs input guardrails (intent, content, rate limit)
3. Creates `CrawlJob` with status QUEUED
4. Runs the agent graph
5. Streams progress via SSE
6. Stores result in cache + completes idempotency

---

## Files Created

```
src/agent/
├── state.py
├── graph.py
└── nodes/
    ├── plan.py
    ├── execute.py
    ├── evaluate.py
    └── synthesize.py

src/guardrails/
├── input/
│   ├── classifier.py
│   └── rate_limiter.py
└── output/
    ├── pii.py
    └── grounding.py

src/api/routes/
└── search.py
```
