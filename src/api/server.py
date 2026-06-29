from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from src.api.routes.health import router as health_router
from src.common.errors import AppError
from src.config.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings

    es = AsyncElasticsearch(
        hosts=[f"http://{settings.es_host}:{settings.es_port}"],
    )
    redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )

    app.state.es = es
    app.state.redis = redis

    yield

    await es.close()
    await redis.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="Accommodation Discovery Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.settings = settings

    app.include_router(health_router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": exc.message, "code": exc.code},
        )

    return app
