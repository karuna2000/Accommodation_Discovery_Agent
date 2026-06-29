# Technology Stack

**Date:** June 29, 2026

---

## Languages & Runtimes

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Backend (FastAPI, MCP, tools, agent) |
| TypeScript | 5.x | Frontend (React) |
| HTML / CSS | — | Frontend structure + Tailwind utility classes |

---

## Backend Frameworks & Libraries

| Library | Purpose |
|---|---|
| **FastAPI** | API framework (uvicorn ASGI server) |
| **MCP Python SDK** (`mcp`) | FastMCP server for tool definitions |
| **LangGraph** (`langgraph`) | Agent orchestration — state graph, planning → execute → evaluate loop |
| **LangChain AWS** (`langchain-aws`) | Bedrock Claude + Titan integration as LangGraph-compatible LLM |
| **Pydantic v2** | Data models, request/response validation, settings management |
| **httpx** | Async HTTP client (Brave Search, FireCrawl API calls) |
| **elasticsearch-py** | ES 8.x client (index, search, bulk operations) |
| **redis-py** | Redis client (job queue, semantic cache) |
| **boto3** | AWS SDK (Bedrock, S3) |
| **structlog** | Structured JSON logging |
| **python-dotenv** | Local env var management |

---

## Frontend

| Technology | Purpose |
|---|---|
| **Vite** | Build tool + dev server |
| **React** | UI framework |
| **TypeScript** | Type safety |
| **Tailwind CSS** | Utility-first styling |

---

## Data Stores

| Technology | Purpose |
|---|---|
| **Elasticsearch 8.x** | Crawled property cache (24hr TTL), hybrid search (geo + vector + BM25) |
| **Redis** | Job queue + status store, semantic cache (cosine similarity) |

---

## AWS Services

| Service | Purpose |
|---|---|
| **EC2 t3.micro** | Compute — FastAPI + ES + Redis |
| **S3** | Frontend static files + crawled images |
| **CloudFront** | CDN — frontend + `/api/*` proxy to EC2 |
| **Bedrock** | Claude 3 Sonnet (agent, extraction, synthesis) + Titan Embeddings v2 |
| **CloudWatch** | Logging + monitoring |
| **IAM** | Permissions (EC2 instance role) |

---

## External APIs

| API | Purpose |
|---|---|
| **Brave Search API** | URL discovery — find listing pages from user query |
| **FireCrawl API** | Web scraping — JS-rendered page to clean markdown |

---

## DevOps & Tooling

| Tool | Purpose |
|---|---|
| **Docker + docker-compose** | Local dev environment (ES, Redis, FastAPI) |
| **Makefile** | Task runner (dev, test, lint, clean) |
| **nginx** | Reverse proxy on EC2 (CloudFront → FastAPI) |
| **GitHub Actions** | CI/CD — frontend → S3, backend → EC2 deploy |
| **pytest** | Backend testing |
| **ruff** | Python linter + formatter |

---

## Not Used (explicitly excluded)

| Technology | Why not |
|---|---|
| DynamoDB | No long-term storage needed; ES handles everything |
| API Gateway | CloudFront → EC2 directly, simpler + no cold starts |
| Lambda | Everything on EC2; no event-driven functions needed |
| SQS | Background tasks run in-process (single EC2) |
| Celery / RQ | Overkill for single-instance POC; Python thread pool suffices |
| FastAPI ECS/Fargate | Free-tier limits; single EC2 is enough for POC |
| PostgreSQL | No relational data to store |
| Playwright | FireCrawl handles JS rendering as a managed API |
