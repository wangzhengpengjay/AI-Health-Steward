"""Feishu channel CRUD + connection status."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.feishu import FeishuChannel
from app.services.feishu import feishu_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feishu", tags=["feishu"])


def _mask(s: str) -> str:
    return "******" if s else ""


def _to_dict(ch: FeishuChannel) -> dict:
    return {
        "id": ch.id,
        "name": ch.name,
        "app_id": ch.app_id[:8] + "..." if ch.app_id else "",
        "app_secret_masked": _mask(ch.app_secret),
        "member_id": ch.member_id,
        "is_active": ch.is_active,
    }


class ChannelCreate(BaseModel):
    name: str
    app_id: str
    app_secret: str
    member_id: Optional[int] = None
    is_active: bool = True


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    member_id: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/channels")
async def list_channels(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(FeishuChannel).order_by(FeishuChannel.id))
    channels = result.scalars().all()

    # Attach connection status + bound member name
    conn_map = {cid: c.connected for cid, c in feishu_bot.connections.items()}
    out = []
    for ch in channels:
        d = _to_dict(ch)
        d["connected"] = conn_map.get(ch.id, False)
        # Get member name
        if ch.member_id:
            m = await db.get(FamilyMember, ch.member_id)
            d["member_name"] = m.name if m and not m.is_deleted else None
        else:
            d["member_name"] = None
        out.append(d)
    return out


@router.post("/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChannelCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ch = FeishuChannel(
        name=payload.name,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        member_id=payload.member_id,
        is_active=payload.is_active,
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)

    # Start connection if active
    if ch.is_active:
        await feishu_bot.reload()

    return _to_dict(ch)


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: int,
    payload: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ch = await db.get(FeishuChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")

    changed_config = False
    for field, val in payload.model_dump(exclude_unset=True).items():
        if val is None:
            continue
        # Skip placeholders sent by frontend when user didn't change secret/id
        if field in ("app_secret", "app_id") and val == "__unchanged__":
            continue
        if field in ("app_id", "app_secret"):
            changed_config = True
        setattr(ch, field, val)

    await db.commit()
    await db.refresh(ch)

    # Reload if any config field changed (app_id/secret/member_id/is_active)
    if changed_config or payload.is_active is not None or payload.member_id is not None:
        await feishu_bot.reload()

    return _to_dict(ch)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_200_OK)
async def delete_channel(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ch = await db.get(FeishuChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="渠道不存在")

    await db.delete(ch)
    await db.commit()

    await feishu_bot.reload()
    return {"deleted": True, "id": channel_id}


@router.post("/reload")
async def reload_channels() -> dict:
    """Reload all channel connections from DB."""
    await feishu_bot.reload()
    return {"ok": True, "connections": feishu_bot.get_status()}


@router.get("/status")
async def feishu_status() -> dict:
    """Return overall Feishu bot status."""
    return {
        "channels": feishu_bot.get_status(),
        "total_active": len(feishu_bot.connections),
    }
