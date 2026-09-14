"""Settings endpoints: provider config read/write, health check, data export, data wipe."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.models.assessments import ScaleResult  # noqa: F401  (registers metadata)
from app.models.family import FamilyMember  # noqa: F401
from app.models.health import (  # noqa: F401
    Allergy,
    ChatMessage,
    CheckupReport,
    Diagnosis,
    FamilyHistory,
    Lifestyle,
    Medication,
    MetricRecord,
    ReportRecord,
)
from app.models.summaries import HealthSummary  # noqa: F401
from app.models.tasks import HealthTask  # noqa: F401
from app.providers.router import ModelRouter, get_model_router

router = APIRouter(prefix="/settings", tags=["settings"])

logger = logging.getLogger(__name__)

# Tables that hold family health data. Derived from the ORM metadata instead of
# a hand-maintained list: the previous hardcoded list silently omitted
# surgeries, vaccinations, report_chunks and data_provenances, so "导出全部数据"
# lost records and "清除所有健康数据" left them in the database.
# Config-only tables are excluded on purpose — channel credentials are not
# health data and should survive an export/wipe cycle.
_CONFIG_ONLY_TABLES = {"alembic_version", "feishu_channels"}


def _health_tables() -> list[Any]:
    """Health-data tables in dependency order (parents before children)."""
    return [t for t in Base.metadata.sorted_tables if t.name not in _CONFIG_ONLY_TABLES]



def _mask(s: str) -> str:
    """Mask a secret with fixed 6 asterisks."""
    if not s:
        return ""
    return "******"


# ---- Provider config read ----

@router.get("/providers")
async def get_provider_config() -> dict[str, Any]:
    """Return masked provider configuration for display."""
    _s = get_settings()
    return {
        "multimodal_api": {
            "base_url": _s.MULTIMODAL_API_BASE,
            "api_key": _mask(_s.MULTIMODAL_API_KEY),
            "model": _s.MULTIMODAL_API_MODEL,
            "is_configured": bool(_s.MULTIMODAL_API_KEY),
        },
        "text_api": {
            "base_url": _s.TEXT_API_BASE,
            "api_key": _mask(_s.TEXT_API_KEY),
            "model": _s.TEXT_API_MODEL,
            "is_configured": bool(_s.TEXT_API_KEY),
        },
        "local_llm": {
            "base_url": _s.LOCAL_LLM_BASE,
            "model": _s.LOCAL_LLM_MODEL,
            "is_configured": True,
        },
        "text_provider_priority": _s.TEXT_PROVIDER_PRIORITY,
        "embedding": {
            "base_url": _s.EMBEDDING_API_BASE or _s.TEXT_API_BASE,
            "api_key": _mask(_s.EMBEDDING_API_KEY or _s.TEXT_API_KEY),
            "model": _s.EMBEDDING_MODEL,
            "is_configured": bool(_s.EMBEDDING_MODEL),
        },
    }


# ---- Provider config write ----

class ProviderUpdatePayload(BaseModel):
    """Payload for updating model provider config. Only non-None fields are updated."""
    multimodal_api_base: Optional[str] = None
    multimodal_api_key: Optional[str] = None
    multimodal_api_model: Optional[str] = None
    text_api_base: Optional[str] = None
    text_api_key: Optional[str] = None
    text_api_model: Optional[str] = None
    local_llm_base: Optional[str] = None
    local_llm_model: Optional[str] = None
    text_provider_priority: Optional[str] = None
    embedding_api_base: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_model: Optional[str] = None


# Maps payload field names to .env variable names
_FIELD_TO_ENV: dict[str, str] = {
    "multimodal_api_base": "MULTIMODAL_API_BASE",
    "multimodal_api_key": "MULTIMODAL_API_KEY",
    "multimodal_api_model": "MULTIMODAL_API_MODEL",
    "text_api_base": "TEXT_API_BASE",
    "text_api_key": "TEXT_API_KEY",
    "text_api_model": "TEXT_API_MODEL",
    "local_llm_base": "LOCAL_LLM_BASE",
    "local_llm_model": "LOCAL_LLM_MODEL",
    "text_provider_priority": "TEXT_PROVIDER_PRIORITY",
    "embedding_api_base": "EMBEDDING_API_BASE",
    "embedding_api_key": "EMBEDDING_API_KEY",
    "embedding_model": "EMBEDDING_MODEL",
}


def _update_env_file(env_path: str, updates: dict[str, str]) -> None:
    """Write updated key-value pairs into .env file, preserving other lines."""
    if not os.path.isfile(env_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f".env file not found at {env_path}",
        )

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Parse KEY=VALUE
        match = re.match(r"^([A-Z_]+)=(.*)$", stripped)
        if match:
            key = match.group(1)
            if key in updates:
                val = updates[key]
                new_lines.append(f"{key}={val}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    # Append any keys that weren't already in the file
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


@router.put("/providers")
async def update_provider_config(payload: ProviderUpdatePayload) -> dict[str, Any]:
    """Update model provider config in .env file and reload settings."""
    updates: dict[str, str] = {}
    for field, env_key in _FIELD_TO_ENV.items():
        val = getattr(payload, field)
        if val is not None:
            updates[env_key] = val

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    env_path = get_settings().env_file_path
    _update_env_file(env_path, updates)

    # Also update process environment variables, because Pydantic Settings
    # prioritizes os.environ over .env file values
    for key, val in updates.items():
        os.environ[key] = val

    # Clear cached singletons so next request rebuilds with new values
    from app.core.config import get_settings as _gs
    from app.providers.router import get_model_router as _gmr
    _gs.cache_clear()
    _gmr.cache_clear()

    return {
        "updated": True,
        "fields": list(updates.keys()),
        "message": "配置已写入 .env 并即时生效",
    }


# ---- Health check ----

@router.get("/providers/health")
async def providers_health(
    router_dep: ModelRouter = Depends(get_model_router),
) -> dict[str, Any]:
    """Health-check each configured provider."""
    results: dict[str, Any] = {}
    if router_dep.multimodal_provider.is_configured:
        results["multimodal_api"] = await router_dep.multimodal_provider.health_check()
    if router_dep.text_api_provider.is_configured:
        results["text_api"] = await router_dep.text_api_provider.health_check()
    if router_dep.local_llm_provider.is_configured:
        results["local_llm"] = await router_dep.local_llm_provider.health_check()
    from app.providers.embedding import EmbeddingProvider
    emb = EmbeddingProvider()
    if emb.is_configured:
        results["embedding"] = await emb.health_check()
    return results


# ---- Data export ----

@router.get("/export")
async def export_all_data(db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Export all family health data as a single JSON file."""
    tables = _health_tables()
    payload: dict[str, Any] = {
        "_meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "app_version": "0.1.0",
            "tables": [t.name for t in tables],
        }
    }
    for table in tables:
        rows = (await db.execute(select(table))).mappings().all()
        payload[table.name] = [dict(row) for row in rows]

    content = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    filename = f"health-data-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Data wipe ----

def _purge_user_files() -> int:
    """Delete stored report files so a wipe removes health data, not just rows.

    Refuses to touch a filesystem root or the user's home directory: a
    misconfigured USERDATA_DIR must never turn "clear health data" into a
    destructive wipe of unrelated files.
    """
    import shutil
    from pathlib import Path

    settings_obj = get_settings()
    unsafe = {Path("/").resolve(), Path.home().resolve()}
    removed = 0
    roots = {
        Path(settings_obj.USERDATA_DIR).expanduser(),
        Path(settings_obj.UPLOAD_DIR).expanduser(),
    }
    for root in roots:
        if not root.is_dir():
            continue
        if root.resolve() in unsafe:
            logger.error("Refusing to purge unsafe directory: %s", root)
            continue
        for child in root.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("Failed to remove %s during wipe: %s", child, exc)
    return removed


@router.delete("/data", status_code=status.HTTP_200_OK)
async def wipe_all_data(
    # No default: the guard must not be satisfiable by omitting the parameter.
    # With `confirm: str = "DELETE"` a bare DELETE /settings/data wiped the
    # entire database, making the "requires explicit confirmation" contract
    # meaningless.
    confirm: str = "",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete ALL health data (rows + stored files). Requires confirm=DELETE."""
    if confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="需要显式确认：请携带 ?confirm=DELETE",
        )
    deleted: dict[str, int] = {}
    # Reverse dependency order so foreign keys stay satisfied.
    for table in reversed(_health_tables()):
        result = await db.execute(delete(table))
        deleted[table.name] = result.rowcount or 0
    await db.commit()
    files_removed = _purge_user_files()
    return {
        "deleted": True,
        "tables": deleted,
        "files_removed": files_removed,
        "message": "所有健康数据已清除",
    }


# ---- User data directory ----

@router.get("/userdata")
async def get_userdata_config() -> dict[str, Any]:
    """Return current userdata directory path."""
    return {
        "userdata_dir": get_settings().USERDATA_DIR,
        "exists": os.path.isdir(get_settings().USERDATA_DIR),
    }


class UserDataPathUpdate(BaseModel):
    new_path: str


@router.put("/userdata")
async def update_userdata_path(payload: UserDataPathUpdate) -> dict[str, Any]:
    """Move userdata directory to a new location and update .env."""
    import shutil
    from pathlib import Path

    old_path = Path(get_settings().USERDATA_DIR)
    new_path = Path(payload.new_path).expanduser().resolve()

    if new_path == old_path:
        return {"updated": False, "message": "新路径与当前路径相同"}

    new_path.mkdir(parents=True, exist_ok=True)

    # Move contents
    if old_path.exists() and old_path != new_path:
        for item in old_path.iterdir():
            dest = new_path / item.name
            if dest.exists():
                shutil.rmtree(str(dest)) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), str(dest))

    # Update .env
    env_path = get_settings().env_file_path
    _update_env_file(env_path, {"USERDATA_DIR": str(new_path)})
    os.environ["USERDATA_DIR"] = str(new_path)

    # Clear cache so settings reload
    from app.core.config import get_settings as _gs
    _gs.cache_clear()

    return {
        "updated": True,
        "old_path": str(old_path),
        "new_path": str(new_path),
        "message": (
            "文件已迁移。如果使用 Docker，请同时更新 .env 中的 "
            "USERDATA_HOST_DIR 并重启容器使 bind mount 生效。"
        ),
    }
