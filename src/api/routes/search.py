import json
from hashlib import sha256
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.common.errors import IdempotencyKeyReplayedError, QueryBlockedError, RateLimitError
from src.domain.models.job import CrawlJob, JobStatus
from src.guardrails.input.classifier import validate_input
from src.guardrails.input.rate_limiter import SlidingWindowRateLimiter
from src.guardrails.output.grounding import check_grounding
from src.guardrails.output.pii import strip_pii

router = APIRouter(tags=["search"])

_rate_limiter = SlidingWindowRateLimiter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    max_iterations: int = Field(default=5, ge=1, le=20)
    location_hint: str | None = None


class SearchStatusResponse(BaseModel):
    search_id: str
    status: str
    answer: str | None = None
    error: str | None = None


@router.post("/api/search")
async def search(
    request: Request,
    body: SearchRequest,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    deps = request.app.state.deps
    tools = request.app.state.tools
    bedrock_client = deps.bedrock_client

    ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(ip):
        raise RateLimitError()

    blocked_reason = validate_input(body.query)
    if blocked_reason:
        raise QueryBlockedError(blocked_reason)

    if idempotency_key and deps.idem_repo:
        if not await deps.idem_repo.try_acquire(idempotency_key):
            status = await deps.idem_repo.get_status(idempotency_key)
            if status and status.startswith("completed:"):
                cached = await deps.cache_repo.get_similar(body.query) if deps.cache_repo else None
                if cached:
                    return SearchStatusResponse(
                        search_id=idempotency_key,
                        status="completed",
                        answer=strip_pii(cached.get("response", "")),
                    )
            raise IdempotencyKeyReplayedError(idempotency_key)

    search_id = idempotency_key or str(uuid4())
    job = CrawlJob(search_id=search_id, query=body.query)
    if deps.job_repo:
        await deps.job_repo.create(job)

    tool_schemas = []
    for name, t in tools.items():
        tool_schemas.append({
            "name": name,
            "description": getattr(t, "description", ""),
            "input_schema": getattr(t, "input_schema", {}),
        })

    from src.agent.graph import run_agent

    async def event_stream():
        final_answer = "I couldn't find any results."
        final_error = None
        final_results: list[dict] = []

        async for event in run_agent(
            query=body.query,
            tools=tools,
            tool_schemas=tool_schemas,
            bedrock_client=bedrock_client,
            max_iterations=body.max_iterations,
        ):
            yield f"data: {json.dumps({'type': 'event', 'data': event})}\n\n"

            for node_name, node_data in event.items():
                if isinstance(node_data, dict):
                    if node_data.get("synthesized_answer"):
                        final_answer = node_data["synthesized_answer"]
                    if node_data.get("error"):
                        final_error = node_data["error"]
                    if node_data.get("results"):
                        final_results = node_data["results"]

        if deps.job_repo:
            grounded = True
            grounding_issues: list[str] = []
            if final_answer and final_results:
                grounded, grounding_issues = check_grounding(final_answer, final_results)
            await deps.job_repo.update(
                search_id,
                status=JobStatus.COMPLETE if grounded else JobStatus.ERROR,
                error=final_error or ("; ".join(grounding_issues) if grounding_issues else None),
            )

        final_answer = strip_pii(final_answer)

        if deps.cache_repo:
            await deps.cache_repo.store(
                query=body.query,
                embedding=None,
                response=final_answer,
            )

        if idempotency_key and deps.idem_repo:
            response_hash = sha256(final_answer.encode()).hexdigest()[:12]
            await deps.idem_repo.complete(idempotency_key, response_hash)

        yield f"data: {json.dumps({'type': 'done', 'search_id': search_id, 'answer': final_answer, 'error': final_error})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/search/{search_id}")
async def get_search_status(search_id: str, request: Request):
    deps = request.app.state.deps
    if not deps.job_repo:
        raise HTTPException(503, "Job repository not available")
    job = await deps.job_repo.get(search_id)
    if not job:
        raise HTTPException(404, "Search not found")
    return SearchStatusResponse(
        search_id=job.search_id,
        status=job.status.value,
        error=job.error,
    )


@router.post("/api/search/{search_id}/cancel")
async def cancel_search(search_id: str, request: Request):
    deps = request.app.state.deps
    if not deps.job_repo:
        raise HTTPException(503, "Job repository not available")
    job = await deps.job_repo.get(search_id)
    if not job:
        raise HTTPException(404, "Search not found")
    if job.status in (JobStatus.COMPLETE, JobStatus.CANCELLED, JobStatus.ERROR):
        raise HTTPException(400, f"Search already in terminal state: {job.status.value}")

    cancel_registry = getattr(deps, "cancel_registry", None)
    if cancel_registry and search_id in cancel_registry:
        cancel_registry[search_id].set()

    await deps.job_repo.update(search_id, status=JobStatus.CANCELLED)
    return {"status": "cancelled", "search_id": search_id}
