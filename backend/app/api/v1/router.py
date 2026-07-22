"""Aggregate all v1 route modules."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import members, metrics, providers
from app.api.routes import chat

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(members.router)
api_router.include_router(metrics.router)
api_router.include_router(providers.router)
api_router.include_router(chat.router)
