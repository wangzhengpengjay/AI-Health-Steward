"""Aggregate all v1 route modules."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_auth

from app.api.routes import members, metrics, providers
from app.api.routes import chat
from app.api.routes import profile
from app.api.routes import reports
from app.api.routes import checkup
from app.api.routes import settings
from app.api.routes import feishu
from app.api.routes import tasks
from app.api.routes import summaries

# P0-3: 所有业务接口在配置了 AUTH_TOKEN 时要求 Bearer 令牌；未配置时保持开放。
api_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_auth)],
)
api_router.include_router(members.router)
api_router.include_router(metrics.router)
api_router.include_router(providers.router)
api_router.include_router(chat.router)
api_router.include_router(profile.router)
api_router.include_router(reports.router)
api_router.include_router(checkup.router)
api_router.include_router(settings.router)
api_router.include_router(feishu.router)
api_router.include_router(tasks.router)
api_router.include_router(summaries.router)
