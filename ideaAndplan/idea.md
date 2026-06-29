# Project Architecture & Solution Report: AI-Powered Discovery Platform
**Date:** June 29, 2026
**Subject:** High-Level Design and Solution Specification for a Massive-Scale AI Accommodation Discovery Engine

---

## 1. Core Platform Philosophy
The platform has evolved into an **authoritative, two-sided discovery marketplace**. By abandoning transactional booking flows in favor of pure discovery, the architecture optimizes for **extreme read throughput** and **sub-second AI response latency**. The core design principle is the decoupling of high-frequency owner-driven updates from high-volume student-driven search queries.

---

## 2. Technical Architecture Overview



### The Stack
* **API/Logic Layer:** FastAPI on AWS ECS (Fargate).
* **Primary Ledger (Writes):** Amazon DynamoDB (NoSQL).
* **Discovery Engine (Reads):** Elasticsearch (OpenSearch).
* **Sync Logic:** DynamoDB Streams + AWS Lambda (Serverless).
* **Intelligence Layer:** LLM-based intent parsing + Semantic Caching (Redis).

---

## 3. Data Flow & Synchronization
We utilize an **Event-Driven Synchronization Pattern** to ensure the search index is always performant without locking the primary database.

1.  **Ingestion:** Property owners update data via an Owner UI. Data is committed to **DynamoDB** (optimized for write-heavy key-value operations).
2.  **CDC (Change Data Capture):** **DynamoDB Streams** detects the change immediately.
3.  **Sync Pipeline:** A **Lambda function** triggers on the stream. It performs:
    * **LLM Enrichment:** Generates vector embeddings for property descriptions.
    * **Auto-Tagging:** Extracts categorical features (e.g., "social vibe," "study-focused").
    * **Elasticsearch Update:** Pushes the enriched document into the discovery index.
4.  **Discovery:** When a user searches, the **AI Agent** interacts *only* with **Elasticsearch**, ensuring no multi-database join latency.

---

## 4. Search & Intelligence Strategy

### Agentic Reasoning vs. Autonomous Loops
To maintain speed and cost-predictability, the system uses **Single-Turn Agentic Reasoning**:
* **Intent Layer:** A fast, cost-efficient LLM translates natural language into a structured JSON query.
* **Execution Layer:** A single, optimized hybrid query to Elasticsearch (Spatial + Vector + Boolean filters).
* **Synthesis Layer:** The LLM summarizes the retrieved data into a conversational response.
* *Note: Autonomous agentic loops are avoided to prevent unpredictable latency and cost spirals.*

### Semantic Caching
To handle thousands of users asking for the same thing in different ways, we implement **Semantic Caching (Redis)**:
* Queries are embedded and checked for similarity (>0.90 cosine similarity) against previous requests.
* **Cache Hit:** Returns a pre-generated response in ~20ms, bypassing the LLM entirely.
* **Cache Miss:** LLM processes the query, caches the result, and serves the user.

---

## 5. Architectural Tradeoffs & Decisions

| Decision | Tradeoff | Rationale |
| :--- | :--- | :--- |
| **DynamoDB (Primary)** | Rigid (No complex Joins) | Superior horizontal scaling and seamless CDC for sync. |
| **Elasticsearch (Search)** | Operational Complexity | Necessary for hybrid search (Geo + Vector + BM25) at scale. |
| **Split Storage** | Synchronization Risk | Offloads heavy reads from the transactional ledger. |
| **Agentic Reasoning** | Limited Autonomy | Predictable latency/cost vs. non-deterministic loops. |

---

## 6. Guardrails & Safety
To ensure production-grade stability, we implement a "Safety Sandwich" :
* **Input Guardrails:** Sanitizes prompts, blocks non-accommodation intent, and enforces strict JSON schema validation.
* **Output Guardrails:** Ensures the LLM summary relies **strictly on retrieved data** (Grounding) and filters PII/toxic content.
* **Implementation:** Lightweight, local models (e.g., Llama 3.2 1B) are used for safety checks to minimize inference costs.

---

## 7. Cost Management Strategy
* **Ingestion (Owner-side):** Low volume. Uses higher-quality models to ensure perfect indexing.
* **Discovery (Student-side):** High volume. Uses the cheapest "Flash" class models combined with aggressive **Semantic Caching** to minimize total token consumption.

---

## 8. Conclusion
By separating the **Write Ledger (DynamoDB)**, **Discovery Engine (Elasticsearch)**, and **Semantic Cache (Redis)**, the system is designed to scale horizontally without incurring the prohibitive latency of traditional relational databases or the cost volatility of unoptimized agentic AI.