# AWS Services List (Revised — Pure Crawl-Based Architecture)

## Free Tier Services Used

| Service | Configuration | Purpose |
|---|---|---|
| **EC2** | t3.micro, 30GB EBS, 750 hrs/mo | FastAPI + Elasticsearch + Redis (all on one box) |
| **S3** | 5GB storage, 20K GET/mo, 2K PUT/mo | React frontend hosting + crawled images |
| **CloudFront** | 1TB transfer/mo, 10M requests/mo | CDN for frontend + `/api/*` proxy to EC2 |
| **Bedrock** | Claude 3 Sonnet + Titan Embeddings ($200 credits) | Intent parsing, synthesis, extraction, embeddings |
| **CloudWatch** | 5GB logs/mo, 10 metrics, 10 alarms | Application logging + monitoring |
| **IAM** | Free | Roles and instance profile permissions |

## External Services

| Service | Cost | Purpose |
|---|---|---|
| **Brave Search API** | Free $5 credits/mo | URL discovery from user query |
| **FireCrawl API** | Free tier (500 credits/mo) | JS-rendered page scraping |
| **Elasticsearch** | Self-managed on EC2 (free) | 24hr rotating cache + hybrid search |

## Removed (v1 → v2)

- ❌ DynamoDB — no long-term storage needed
- ❌ API Gateway — traffic goes CloudFront → EC2 directly
- ❌ Lambda — everything runs on EC2
- ❌ SQS — no async queue needed (in-process background tasks)
- ❌ Comprehend — LLM handles extraction directly
- ❌ Textract — no document processing
- ❌ Secrets Manager — API keys in env vars on EC2
