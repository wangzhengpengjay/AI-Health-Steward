"""Aggregate all v1 route modules."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import members, metrics, providers
from app.api.routes import chat
from app.api.routes import profile
from app.api.routes import reports
from app.api.routes import checkup

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(members.router)
api_router.include_router(metrics.router)
api_router.include_router(providers.router)
api_router.include_router(chat.router)
api_router.include_router(profile.router)
api_router.include_router(reports.router)
api_router.include_router(checkup.router)
