"""Regression tests for long-term memory compaction.

The compactor reads only the oldest ``_MAX_COMPACT_MESSAGES`` per pass, so the
watermark must advance to the last message it actually summarized. Setting it to
``datetime.now()`` marked the rest of the backlog as done and dropped it from
long-term memory permanently.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services import member_memory


def _msg(idx: int, when: datetime, role: str = "user") -> SimpleNamespace:
    return SimpleNamespace(id=idx, role=role, content=f"msg-{idx}", created_at=when)


def _run(rows, *, existing_summary=None, count=None, reply="更新后的记忆"):
    """Drive maybe_compact_memory with mocked DB + provider."""
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

    member = SimpleNamespace(
        id=1,
        memory_summary=existing_summary,
        memory_summary_updated_at=base if existing_summary else None,
    )

    count_result = MagicMock()
    count_result.scalar_one.return_value = len(rows) if count is None else count

    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = rows

    db = AsyncMock()
    db.get.return_value = member
    db.execute.side_effect = [count_result, rows_result]

    provider = AsyncMock()
    provider.chat.return_value = SimpleNamespace(content=reply)
    router = MagicMock()
    router.get_text_provider.return_value = provider

    result = asyncio.run(member_memory.maybe_compact_memory(db, router, 1))
    return result, member, db


def test_watermark_advances_to_last_summarized_message():
    """The watermark must be the timestamp of the final row read, not now()."""
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_msg(i, base + timedelta(minutes=i)) for i in range(1, 21)]

    result, member, _db = _run(rows, count=50)

    assert result == "更新后的记忆"
    assert member.memory_summary_updated_at == rows[-1].created_at
    # Crucially it must NOT be "now", which would skip the untouched backlog.
    assert member.memory_summary_updated_at < datetime.now(timezone.utc)
    assert member.memory_summary_updated_at == base + timedelta(minutes=20)


def test_backlog_beyond_one_batch_is_not_skipped():
    """Simulate a 50-message backlog: pass 1 must leave messages 21-50 pending."""
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    all_rows = [_msg(i, base + timedelta(minutes=i)) for i in range(1, 51)]

    # Pass 1 reads the oldest 20.
    result, member, _db = _run(all_rows[:20], count=50)
    assert result == "更新后的记忆"
    watermark_after_pass1 = member.memory_summary_updated_at

    # Messages 21..50 are still newer than the watermark, so they remain pending
    # for the next pass instead of being silently dropped.
    pending = [r for r in all_rows if r.created_at > watermark_after_pass1]
    assert len(pending) == 30
    assert pending[0].id == 21
    assert pending[-1].id == 50


def test_no_compaction_below_threshold():
    """Below the threshold no LLM call happens and the watermark is untouched."""
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_msg(i, base + timedelta(minutes=i)) for i in range(1, 3)]

    result, member, db = _run(rows, existing_summary="既往记忆", count=2)

    assert result == "既往记忆"
    assert member.memory_summary_updated_at == base
    db.flush.assert_not_called()


def test_llm_failure_keeps_previous_summary_and_watermark():
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_msg(i, base + timedelta(minutes=i)) for i in range(1, 21)]

    member = SimpleNamespace(
        id=1, memory_summary="既往记忆", memory_summary_updated_at=base
    )
    count_result = MagicMock()
    count_result.scalar_one.return_value = 50
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = rows

    db = AsyncMock()
    db.get.return_value = member
    db.execute.side_effect = [count_result, rows_result]

    provider = AsyncMock()
    provider.chat.side_effect = RuntimeError("provider down")
    router = MagicMock()
    router.get_text_provider.return_value = provider

    result = asyncio.run(member_memory.maybe_compact_memory(db, router, 1))

    assert result == "既往记忆"
    # Watermark unchanged so the same batch is retried next time.
    assert member.memory_summary_updated_at == base
