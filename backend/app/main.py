"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.services.feishu import feishu_bot
from app.services.summary_scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Feishu channels if any are configured
    asyncio.ensure_future(feishu_bot.start_all())
    # Periodic health-summary auto-generation (natural week/month/year first day)
    scheduler_task = asyncio.ensure_future(scheduler_loop(async_session_factory))
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    await feishu_bot.stop_all()


app = FastAPI(
    title="AI Health Steward API",
    version="0.1.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
