from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class ServiceCheck(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    checks: dict[str, ServiceCheck]


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request):
    checks: dict[str, ServiceCheck] = {}

    es = getattr(request.app.state, "es", None)
    if es is not None:
        try:
            info = await es.info()
            checks["elasticsearch"] = ServiceCheck(
                status="ok",
                detail=f"cluster: {info['cluster_name']}, version: {info['version']['number']}",
            )
        except Exception as e:
            checks["elasticsearch"] = ServiceCheck(status="error", detail=str(e))
    else:
        checks["elasticsearch"] = ServiceCheck(status="not_connected")

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = ServiceCheck(status="ok")
        except Exception as e:
            checks["redis"] = ServiceCheck(status="error", detail=str(e))
    else:
        checks["redis"] = ServiceCheck(status="not_connected")

    checks["app"] = ServiceCheck(status="ok")

    all_ok = all(c.status == "ok" for c in checks.values())

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )
