"""Long-term conversation memory via rolling summarization (P1-4).

Keeps a compact per-member summary of prior consultations so the AI can
recall earlier topics, conditions, medications, preferences, and advice
across sessions — without holding the entire message history in context.

Design:
- A summary is stored on the member row (memory_summary).
- After each assistant reply, if enough *new* messages have accumulated since
  the last compaction, a compact summarizer LLM call merges them into the
  existing summary (incremental). This avoids a full re-read each time.
- The summary is injected into the system prompt at the start of a chat turn.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyMember
from app.models.health import ChatMessage
from app.providers.base import Message
from app.providers.router import ModelRouter

logger = logging.getLogger(__name__)

# Trigger compaction when this many new messages accumulate since last summary.
_COMPACT_THRESHOLD = 6
# Cap how many messages a single compaction pass reads (oldest-first).
_MAX_COMPACT_MESSAGES = 20

MEMORY_SYSTEM_PROMPT = """\
你是一个健康管家，负责把一段家庭健康对话压缩为"长期记忆"要点。
请用简洁的中文要点（每行一条，前缀 - ）总结：
1. 用户提到的身体症状、指标数值、病情
2. 正在服用的药物、剂量、频次
3. 医生/你给出的建议、用户意愿与偏好
4. 需要后续跟进的事项

要求：
- 只总结事实与要点，不编造。
- 若已有【既往记忆】，把它与新对话合并，去重、保留更重要的信息，整体不超过 30 行。
- 只输出要点列表，不要额外解释。
"""


async def get_memory_summary(db: AsyncSession, member_id: int) -> str | None:
    """Return the stored long-term memory summary for a member (or None)."""
    result = await db.execute(
        select(FamilyMember.memory_summary).where(FamilyMember.id == member_id)
    )
    row = result.scalar()
    return row if isinstance(row, str) and row.strip() else None


async def maybe_compact_memory(
    db: AsyncSession,
    router: ModelRouter,
    member_id: int,
    source: str = "webui",
) -> str | None:
    """Compact recent chat messages into the member's long-term memory.

    Called after each assistant reply. Only triggers an LLM call when enough
    new messages have accumulated. Returns the updated summary or None.
    """
    member = await db.get(FamilyMember, member_id)
    if member is None:
        return None

    last_summary_time = member.memory_summary_updated_at
    q = select(func.count()).where(ChatMessage.member_id == member_id)
    if last_summary_time is not None:
        q = q.where(ChatMessage.created_at > last_summary_time)
    count = (await db.execute(q)).scalar_one()

    if count < _COMPACT_THRESHOLD:
        return member.memory_summary

    # Load the unsummarized messages (oldest first).
    q = (
        select(ChatMessage)
        .where(ChatMessage.member_id == member_id)
        .order_by(ChatMessage.created_at.asc())
    )
    if last_summary_time is not None:
        q = q.where(ChatMessage.created_at > last_summary_time)
    rows = (await db.execute(q.limit(_MAX_COMPACT_MESSAGES))).scalars().all()
    if not rows:
        return member.memory_summary

    transcript = "\n".join(f"{r.role}: {r.content}" for r in rows)
    existing = member.memory_summary or "无既往记忆"

    try:
        provider = router.get_text_provider()
        response = await provider.chat(
            [
                Message(role="system", content=MEMORY_SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=(
                        f"【既往记忆】\n{existing}\n\n"
                        f"【本次新增对话】\n{transcript}\n\n"
                        f"请生成更新后的长期记忆要点。"
                    ),
                ),
            ],
            temperature=0.2,
            max_tokens=800,
        )
        new_summary = response.content.strip()
        if not new_summary:
            return member.memory_summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory compaction failed for member %s: %s", member_id, exc)
        return member.memory_summary

    member.memory_summary = new_summary
    member.memory_summary_updated_at = datetime.now(timezone.utc)
    await db.flush()
    return new_summary