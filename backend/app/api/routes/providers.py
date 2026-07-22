"""Model provider status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.providers.router import ModelRouter, get_model_router

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/status")
async def provider_status(router_dep: ModelRouter = Depends(get_model_router)) -> dict:
    """Return configuration status of all model providers."""
    return router_dep.get_provider_status()


@router.get("/health")
async def provider_health(router_dep: ModelRouter = Depends(get_model_router)) -> dict:
    """Health-check each configured provider."""
    results = {}
    if router_dep.multimodal_provider.is_configured:
        results["multimodal_api"] = await router_dep.multimodal_provider.health_check()
    if router_dep.text_api_provider.is_configured:
        results["text_api"] = await router_dep.text_api_provider.health_check()
    if router_dep.local_llm_provider.is_configured:
        results["local_llm"] = await router_dep.local_llm_provider.health_check()
    return results
