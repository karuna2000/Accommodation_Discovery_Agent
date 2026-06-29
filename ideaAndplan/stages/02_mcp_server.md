# Stage 2: MCP Server

**Goal:** A decoupled tool layer where each external capability (web search, scraping, extraction, storage, caching, synthesis) is a pluggable MCP tool.

---

## What We Built

### Files Added

```
src/
├── domain/
│   └── models/
│       ├── property.py       # CrawledProperty (the core entity)
│       ├── search.py         # SearchQuery, SearchResult
│       └── job.py            # CrawlJob, JobStatus enum
├── mcp/
│   ├── server.py             # FastMCP server, registers all tools
│   ├── registry.py           # ToolRegistry with decorator-based registration
│   └── tools/
│       ├── base.py           # BaseTool ABC
│       ├── brave_search.py   # search_web(query) → [url]
│       ├── firecrawl.py      # scrape_url(url) → markdown
│       ├── extraction.py     # extract_property(markdown) → CrawledProperty
│       ├── es.py             # search_es + store_property
│       ├── cache.py          # search_cache + store_cache
│       └── synthesize.py     # synthesize_answer(data) → str
├── api/
│   └── routes/
│       ├── search.py         # placeholder search routes
│       └── __init__.py
├── infrastructure/
│   └── persistence/
│       ├── elasticsearch/
│       │   ├── client.py     # ES client factory
│       │   ├── repository.py # SearchRepository stub impl
│       │   └── index_manager.py
│       └── redis/
│           ├── client.py     # Redis client factory
│           ├── cache_repository.py
│           └── job_repository.py
```

---

## How Each Piece Works

### Domain Models

**`CrawledProperty`** — The core entity. Every scraped listing becomes one of these.

```python
class CrawledProperty(BaseModel):
    property_id: str = Field(default_factory=lambda: str(uuid4()))
    source_url: str
    source_site: str
    title: str
    description: str | None = None
    location: Location | None = None
    price_monthly: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    amenities: list[str] = []
    tags: list[str] = []
    images: list[str] = []
    reviews_summary: str | None = None
    embedding: list[float] | None = None
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 0.5
```

Key design choices:
- **Nullable fields** — Most scraped listings will have missing data. `None` means "not available" rather than defaulting to 0 or empty string.
- **`property_id` auto-generated** — UUID string, no collision risk.
- **`crawled_at` UTC** — Timestamp for TTL cleanup.
- **`confidence`** — Ratio of populated fields (0.0 = all null, 1.0 = all filled). Helps the agent decide result quality.

**`Location`** — Embedded in CrawledProperty.

```python
class Location(BaseModel):
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
```

**`SearchQuery`** — What the user asks, plus structured filters extracted by the agent.

```python
class SearchQuery(BaseModel):
    raw: str
    location_hint: str | None = None
    max_price: float | None = None
    min_bedrooms: int | None = None
    tags: list[str] = []
```

**`CrawlJob`** — Tracks async search progress.

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    SEARCHING = "searching"
    SCRAPING = "scraping"
    EXTRACTING = "extracting"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"

class CrawlJob(BaseModel):
    search_id: str
    query: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    total_steps: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
```

### BaseTool — Abstract Base Class

All MCP tools inherit from `BaseTool`:

```python
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict

    def __init__(self, deps: ToolDependencies):
        self._deps = deps

    @abstractmethod
    async def run(self, **kwargs) -> Any: ...
```

Each tool declares:
- `name` — How the agent references it (snake_case)
- `description` — Natural language description for the LLM to understand what the tool does
- `input_schema` — JSON Schema describing parameters
- `run()` — Async execution method

### ToolRegistry

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, type[BaseTool]] = {}

    def register(self, tool_cls: type[BaseTool]):
        self._tools[tool_cls.name] = tool_cls

    def create_all(self, deps: ToolDependencies) -> dict[str, BaseTool]:
        return {name: cls(deps) for name, cls in self._tools.items()}

    def get_schemas(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in self._tools.values()]

# Global registry singleton
registry = ToolRegistry()

# Decorator for convenient registration
def tool(cls):
    registry.register(cls)
    return cls
```

Usage:
```python
@tool
class BraveSearchTool(BaseTool):
    name = "search_web"
    description = "Search the web for accommodation listings"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Number of results"},
        },
        "required": ["query"],
    }

    async def run(self, query: str, count: int = 10) -> list[str]:
        return await self._deps.brave_client.search(query, count=count)
```

### The 7 Tools

| Tool | Name | What it does | Stub behavior |
|---|---|---|---|
| **BraveSearchTool** | `search_web` | Calls Brave Search API → returns URLs | Returns mock URLs |
| **FirecrawlTool** | `scrape_url` | Calls FireCrawl API → returns markdown | Returns mock markdown |
| **ExtractionTool** | `extract_property` | Claude extracts structured data from markdown | Returns mock CrawledProperty |
| **ESTool** | `search_es` | Hybrid ES query (knn + geo + filters) | Returns empty list |
| **ESTool** | `store_property` | Indexes a CrawledProperty into ES | No-op |
| **CacheTool** | `search_cache` | Redis semantic cache lookup | Returns None (miss) |
| **CacheTool** | `store_cache` | Stores response + embedding in Redis | No-op |
| **SynthesizeTool** | `synthesize_answer` | Claude generates conversational response | Returns mock answer |

Each tool has a stub implementation that returns realistic-looking data. When real API keys are added (Stage 3+), the stub is replaced by calling the actual `infrastructure.external` client.

### MCP Server Setup

```python
# src/mcp/server.py
from mcp.server.fastmcp import FastMCP

def create_mcp_server(tools: dict[str, BaseTool]) -> FastMCP:
    mcp = FastMCP("accommodation-agent")

    for tool in tools.values():
        mcp.add_tool(tool.run, name=tool.name, description=tool.description)

    return mcp
```

The `FastMCP` instance is created once at startup and all tools are registered via `add_tool()`. It uses SSE transport by default when run as a subprocess, but for our embedded use case, we mount it as a FastAPI sub-app.

### Integration with FastAPI

In the app factory (`src/api/server.py`):

```python
@app.on_event("startup")
async def startup():
    settings = app.state.settings

    # Create infrastructure clients
    es_client = AsyncElasticsearch(...)
    redis = Redis(...)

    # Create dependencies for tools
    deps = ToolDependencies(...)

    # Discover and instantiate tools
    tools = registry.create_all(deps)

    # Create MCP server
    mcp_server = create_mcp_server(tools)

    # Mount MCP SSE endpoint
    app.mount("/mcp", mcp_server.sse_app())

    app.state.es = es_client
    app.state.redis = redis
    app.state.tools = tools
    app.state.mcp = mcp_server
```

This means the MCP server is accessible at `http://localhost:8000/mcp` via SSE. Tools can be called directly via the MCP protocol, or through the LangGraph agent which wraps the MCP client.

---

## How to Verify

```bash
make shell
python -c "
from src.mcp.registry import registry
tools = registry.create_all(...)
print([t.name for t in tools.values()])
# → ['search_web', 'scrape_url', 'extract_property', 'search_es', ...]
"
```

## Key Decisions

| Decision | Rationale |
|---|---|
| **Decorator-based registration** | New tools are self-registering. Drop a file in `tools/` with `@tool`, it's automatically discoverable. No manual registration list to update. |
| **BaseTool ABC with type schemas** | The LLM needs structured JSON Schema to know what parameters each tool expects. This is the same format as OpenAI/Claude function calling. |
| **Stub tools from day 1** | Tools return realistic mock data so the agent graph can be tested end-to-end without real API keys. |
| **FastMCP SSE transport** | MCP protocol is standard. SSE allows the LangGraph agent to connect to the tools over HTTP. We could swap to stdio transport later. |
| **ToolDependencies injected** | Tools receive their dependencies at construction (not as globals). This makes testing easy — pass mock dependencies to individual tools. |
| **`domain/models/` as a shared module** | Models are used by tools, API routes, infrastructure, and the agent. A single source of truth prevents drift. |
