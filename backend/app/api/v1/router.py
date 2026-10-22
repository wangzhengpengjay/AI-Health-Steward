"""Aggregate all v1 route modules."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_auth, require_admin

from app.api.routes import members, metrics, providers
from app.api.routes import chat
from app.api.routes import profile
from app.api.routes import reports
from app.api.routes import checkup
from app.api.routes import settings
from app.api.routes import feishu
from app.api.routes import tasks
from app.api.routes import summaries
from app.api.routes import scales
from app.api.routes import visit_prep
from app.api.routes import proactive
from app.api.routes import pairing

# Business API: requires require_auth (localhost or paired device token)
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
api_router.include_router(feishu.router)
api_router.include_router(tasks.router)
api_router.include_router(summaries.router)
api_router.include_router(scales.router)
api_router.include_router(visit_prep.router)
api_router.include_router(proactive.router)

# Admin-only API: requires require_admin (localhost or global AUTH_TOKEN only)
# Paired mobile devices CANNOT access these endpoints — protects API keys,
# provider config, and data wipe operations.
admin_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_admin)],
)
admin_router.include_router(settings.router)

# Pairing endpoints — no require_auth (they handle their own auth)
pairing_router = APIRouter(prefix="/api/v1")
pairing_router.include_router(pairing.router)
