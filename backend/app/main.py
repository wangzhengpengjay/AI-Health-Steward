"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router, pairing_router, admin_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.services.feishu import feishu_bot
from app.services.summary_scheduler import scheduler_loop
from app.services.patrol_engine import patrol_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Feishu channels if any are configured
    asyncio.ensure_future(feishu_bot.start_all())
    # Periodic health-summary auto-generation (natural week/month/year first day)
    scheduler_task = asyncio.ensure_future(scheduler_loop(async_session_factory))
    # V1.4: Proactive health patrol engine
    patrol_task = asyncio.ensure_future(patrol_loop(async_session_factory))
    yield
    scheduler_task.cancel()
    patrol_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await patrol_task
    except asyncio.CancelledError:
        pass
    await feishu_bot.stop_all()


app = FastAPI(
    title="AI Health Steward API",
    version="0.1.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
)

# CORS: Capacitor iOS WKWebView sends Origin: capacitor://localhost
# and Android sends Origin: https://localhost — both are non-standard origins
# that can't be pre-listed. Like openGym, we reflect any Origin back.
# We never send Allow-Credentials (auth is Bearer token, not cookies).
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """Reflect-Origin CORS: allows any origin, supports preflight OPTIONS.
    
    Mirrors openGym's approach:
    - Reflects the requesting Origin back (not '*')
    - Never sends Allow-Credentials (Bearer Token, not cookies)
    - Allows GET, POST, PUT, DELETE, OPTIONS methods
    - Allows Content-Type, Authorization headers
    - OPTIONS preflight returns 204
    """
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin", "")

        # Handle preflight OPTIONS
        if request.method == "OPTIONS" and origin:
            return StarletteResponse(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Max-Age": "600",
                    "Vary": "Origin",
                },
            )

        # Process normal request
        response = await call_next(request)

        # Add CORS headers to actual responses
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"

        return response


app.add_middleware(CORSSecurityMiddleware)

app.include_router(api_router)
app.include_router(admin_router)
app.include_router(pairing_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
