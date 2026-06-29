# Stage 1: Project Scaffold & Local Dev Environment

**Goal:** A working local development environment with all services containerized.

---

## What We Built

### Directory Structure

```
accommodation-discovery-agent/
├── docker-compose.yml       # ES 8.x + Redis + FastAPI
├── Dockerfile                # Python 3.12 container for FastAPI
├── Makefile                  # dev, test, lint, clean commands
├── pyproject.toml            # Project metadata + dependency groups
├── requirements.txt          # Pinned Python dependencies
├── .env.example              # Template for environment variables
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app entry point
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py       # Pydantic BaseSettings (env-based config)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py         # FastAPI app factory
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py     # GET /api/health endpoint
│   └── common/
│       ├── __init__.py
│       └── errors.py         # Base AppError exception
└── tests/
    ├── __init__.py
    └── test_health.py        # Health endpoint test
```

---

## How Each Piece Works

### `docker-compose.yml`

Three services, all on a single Docker network:

| Service | Image | Purpose | Port |
|---|---|---|---|
| `elasticsearch` | `elasticsearch:8.15.0` | Search engine for crawled property storage | 9200 |
| `redis` | `redis:7-alpine` | Cache + job queue + idempotency store | 6379 |
| `api` | Built from `Dockerfile` | FastAPI application | 8000 |

**Elasticsearch** runs in single-node mode with security disabled (development only). The JVM heap is limited to 512MB to fit within the t3.micro's 1GB RAM.

**Redis** is a plain Alpine image — no configuration needed for POC.

**FastAPI** uses a mounted volume (`.:/app`) so code changes trigger auto-reload via uvicorn's `--reload` flag.

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

Key points:
- Uses `python:3.12-slim` — small image, fast builds
- Dependencies installed separately from source code (Docker layer caching)
- `--reload` for hot-reload during development

### `Makefile`

| Command | What it does |
|---|---|
| `make dev` | Starts all services via docker-compose, tail logs |
| `make build` | Rebuilds the FastAPI image |
| `make test` | Runs pytest inside the api container |
| `make lint` | Runs ruff linter |
| `make clean` | Stops services and removes volumes (wipes ES + Redis data) |
| `make shell` | Opens a bash shell in the api container |

### `src/config/settings.py`

Uses Pydantic's `BaseSettings` to load configuration from environment variables (with `.env` file fallback).

```python
class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    es_host: str = "elasticsearch"  # Docker service name
    es_port: int = 9200
    redis_host: str = "redis"       # Docker service name
    redis_port: int = 6379
    ...
    model_config = SettingsConfigDict(env_file=".env")
```

Key: The default `es_host` and `redis_host` point to Docker service names. In production on EC2, these would be `localhost`.

### `src/api/server.py` — App Factory

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Accommodation Discovery Agent")
    app.state.settings = settings or Settings()

    @app.on_event("startup")
    async def startup():
        # Initialize ES client
        # Initialize Redis client
        # Register startup checks

    @app.on_event("shutdown")
    async def shutdown():
        # Close ES connection
        # Close Redis connection

    app.include_router(health_router)
    # Future routers added here

    return app
```

Uses the factory pattern — `create_app()` is called by `main.py`. This makes testing easy (create a fresh app instance per test).

### `src/api/routes/health.py`

Three checks in one endpoint:

```python
@router.get("/api/health")
async def health(request: Request):
    checks = {
        "elasticsearch": await check_es(request.app.state.es),
        "redis": await check_redis(request.app.state.redis),
        "app": {"status": "ok", "version": "0.1.0"},
    }
    all_ok = all(v.get("status") == "ok" for v in checks.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        checks=checks,
    )
```

Returns `200` if all services are healthy, `503` if any are down (with which ones failed).

### `src/common/errors.py`

Base exception hierarchy:

```
AppError (base)
├── QueryBlockedError    (400) — guardrail rejection
├── RateLimitError       (429) — too many requests
├── ServiceError         (base for service failures)
│   ├── ServiceTimeoutError  (504)
│   └── CircuitBreakerOpenError (503)
├── ToolExecutionError   (502) — MCP tool failure
└── IdempotencyKeyReplayedError (409)
```

All caught by a global exception handler in `server.py` that returns consistent JSON:

```json
{"error": "...", "code": "SERVICE_TIMEOUT"}
```

---

## How to Verify It Works

```bash
make dev       # starts everything
make shell     # open bash inside container
curl http://api:8000/api/health
# → {"status": "ok", "checks": {"elasticsearch": {...}, "redis": {...}, "app": {...}}}
```

## Key Decisions

| Decision | Rationale |
|---|---|
| **Settings as env vars** | `SettingsConfigDict(env_file=".env")` — same code works in Docker, EC2, CI without changes |
| **App factory pattern** | Each test gets a fresh `create_app()` instance. No global state pollution between tests. |
| **Health endpoint** | Needed for EC2 target group checks + debugging. Three separate checks (ES, Redis, app) so we know exactly what's down. |
| **Docker service names as defaults** | `es_host: str = "elasticsearch"` means zero config for local dev. In production, set `ES_HOST=localhost`. |
| **Separate requirements.txt** | Simpler for Docker than pyproject.toml (no pipenv/poetry dependency in container) |
