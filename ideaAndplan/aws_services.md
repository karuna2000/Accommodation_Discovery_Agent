# AWS Services List (Revised — Pure Crawl-Based Architecture)

## Free Tier Services Used

| Service | Configuration | Purpose |
|---|---|---|
| **EC2** | t3.micro, 30GB EBS, 750 hrs/mo | FastAPI + Elasticsearch 8.x + Redis + SearXNG + Crawl4AI (all on one box via docker-compose) |
| **S3** | 5GB storage, 20K GET/mo, 2K PUT/mo | React frontend hosting (static assets only; images reference original source URLs, no rehosting) |
| **CloudFront** | 1TB transfer/mo, 10M requests/mo | CDN for frontend + `/api/*` proxy to EC2 (no API Gateway) |
| **Bedrock** | Amazon Nova Micro (`us.amazon.nova-micro-v1:0`) + Cohere Embed v4 (`us.cohere.embed-v4:0`) via $200 credits | Intent parsing, extraction, synthesis (primary), embeddings |
| **Route53** | 50 hosted zones, 1M queries/mo | Custom domain for CloudFront distribution (Stage 7) |
| **CloudWatch** | 5GB logs/mo, 10 metrics, 10 alarms | Application logging + monitoring |
| **IAM** | Free | Roles and instance profile permissions |

## Self-Hosted Services (on EC2 via docker-compose)

| Service | Configuration | Purpose |
|---|---|---|
| **Elasticsearch 8.x** | docker.elastic.co/elasticsearch/elasticsearch:8.11.1, 512MB heap, single-node | 24h rotating cache (`properties-YYYY.MM.DD` indices) + hybrid search |
| **Redis 7** | redis:7-alpine | Idempotency keys (24h TTL), cost tracking (daily counters), job state, result caching |
| **SearXNG** | searxng/searxng:latest, DuckDuckGo + Startpage + Wikipedia engines | URL discovery from user query (replaces Brave Search API) |
| **Crawl4AI** | unclecode/crawl4ai:latest | JS-rendered page scraping → markdown output (replaces FireCrawl API) |

## External / Legacy Services (Optional — Replaced by Self-Hosted)

| Service | Cost | Status |
|---|---|---|
| **Brave Search API** | Free $5 credits/mo | ❌ Replaced by self-hosted SearXNG (legacy client kept for compatibility) |
| **FireCrawl API** | Free tier (500 credits/mo) | ❌ Replaced by self-hosted Crawl4AI (legacy client kept for compatibility) |

## LLM / Embedding Models

| Model | Inference Profile ID | Role |
|---|---|---|
| **Amazon Nova Micro** | `us.amazon.nova-micro-v1:0` | Primary LLM — intent parsing, extraction, synthesis ($0.035/1M tokens) |
| **Claude 3 Haiku** (blocked) | `us.anthropic.claude-3-haiku-20240307-v1:0` | Fallback LLM — blocked; needs Anthropic use case form |
| **Cohere Embed v4** | `us.cohere.embed-v4:0` | Text embeddings for vector search |

## CI/CD Pipeline (GitHub Actions)

### PR / Push to `main` / `stage/*`

| Step | What it runs | Purpose |
|---|---|---|
| **Lint** | `ruff check src/ tests/` | Python style + import sorting |
| **Type check** | `cd frontend && npx tsc --noEmit` | Frontend type safety |
| **Test** | `pytest tests/ -v --cov=src --cov-report=term` | Backend test suite (86 tests) |
| **Build API image** | `docker build -t accom-agent .` | Verify Dockerfile compiles |
| **Build frontend** | `cd frontend && npm ci && npm run build` | Verify frontend compiles |

### Deploy (on push to `main`)

| Step | Action |
|---|---|
| **Frontend → S3** | `aws s3 sync frontend/dist/ s3://$FRONTEND_BUCKET/ --delete` |
| **CloudFront invalidation** | `aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"` |
| **Backend → EC2** | SSH into EC2 → `docker compose pull && docker compose up -d --force-recreate api` |

### Secrets Required

| Secret | Purpose |
|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | S3 sync + CloudFront invalidation |
| `EC2_SSH_KEY` | SSH deploy key for EC2 |
| `EC2_HOST` | EC2 public IP/DNS for remote deploy |
| `FRONTEND_BUCKET` | S3 bucket for frontend assets |
| `CLOUDFRONT_DIST_ID` | CloudFront distribution ID |
| `BEDROCK_AWS_ACCESS_KEY_ID` / `BEDROCK_AWS_SECRET_ACCESS_KEY` | Bedrock inference credentials |

## Removed (v1 → v2 → v3)

- ❌ DynamoDB — no long-term storage needed
- ❌ API Gateway — traffic goes CloudFront → EC2 directly
- ❌ Lambda — everything runs on EC2
- ❌ SQS — no async queue needed (in-process background tasks via LangGraph)
- ❌ Comprehend — LLM + heuristic fallback handles extraction directly
- ❌ Textract — no document processing
- ❌ Secrets Manager — API keys in env vars on EC2
- ❌ Titan Embeddings — replaced by Cohere Embed v4
- ❌ Claude 3 Sonnet — replaced by Nova Micro (primary); Haiku (fallback, blocked)
- ❌ S3 image rehosting — images reference original source URLs only
