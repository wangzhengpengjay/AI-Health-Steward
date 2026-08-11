"""Health summary scheduler — periodic auto-generation.

Triggers a summary on the first day after a natural period ends:
- Monday (natural-week first day)  -> last week's weekly summary
- 1st of month (natural-month)     -> last month's monthly summary
- Jan 1 (natural-year)             -> last year's annual summary

All members are processed. generate_summary decides whether there is
substantive content; an empty period produces a default "no updates" page
WITHOUT calling the LLM. This module owns the *when* + idempotency.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.family import FamilyMember
from app.models.summaries import HealthSummary
from app.services.summary_service import generate_summary

logger = logging.getLogger(__name__)

# Loop re-checks every 6h — also acts as a restart safety net so a process
# restart on a due day still catches the trigger.
CHECK_INTERVAL_SECONDS = 6 * 60 * 60


def _previous_week(today: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the natural week ending yesterday."""
    # Python weekday(): Monday=0 ... Sunday=6
    this_week_monday = today - timedelta(days=today.weekday())
    start = this_week_monday - timedelta(days=7)  # previous Monday
    end = this_week_monday - timedelta(days=1)  # previous Sunday
    return start, end


def _previous_month(today: date) -> tuple[date, date]:
    """Return (1st, last day) of the previous natural month."""
    first_this_month = today.replace(day=1)
    end = first_this_month - timedelta(days=1)  # last day of prev month
    start = end.replace(day=1)
    return start, end


def _previous_year(today: date) -> tuple[date, date]:
    """Return (Jan 1, Dec 31) of the previous natural year."""
    return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)


def _due_periods(today: date) -> list[tuple[str, date, date]]:
    """Which periods are due on this calendar day: (period, start, end) tuples.

    A single day can yield multiple periods (e.g. a Monday that is also the 1st).
    """
    due: list[tuple[str, date, date]] = []
    if today.weekday() == 0:  # Monday = natural-week first day
        start, end = _previous_week(today)
        due.append(("weekly", start, end))
    if today.day == 1:  # 1st = natural-month first day
        start, end = _previous_month(today)
        due.append(("monthly", start, end))
    if today.month == 1 and today.day == 1:  # Jan 1 = natural-year first day
        start, end = _previous_year(today)
        due.append(("annual", start, end))
    return due


async def _summary_exists(
    db: AsyncSession, member_id: int, period: str, start: date, end: date
) -> bool:
    """Idempotency guard: already generated this exact period?"""
    result = await db.execute(
        select(HealthSummary.id).where(
            HealthSummary.member_id == member_id,
            HealthSummary.period == period,
            HealthSummary.period_start == start,
            HealthSummary.period_end == end,
        ).limit(1)
    )
    return result.scalars().first() is not None


async def run_due_summaries(db_factory: async_sessionmaker) -> int:
    """Generate all due periodic summaries for all members. Returns count created."""
    due = _due_periods(date.today())
    if not due:
        return 0

    created = 0
    async with db_factory() as db:
        members = (await db.execute(select(FamilyMember.id))).scalars().all()
        for member_id in members:
            for period, start, end in due:
                if await _summary_exists(db, member_id, period, start, end):
                    continue
                try:
                    await generate_summary(db, member_id, period, start, end)
                    await db.commit()  # scheduler owns its session; persist explicitly
                    created += 1
                except Exception:  # noqa: BLE001
                    await db.rollback()
                    logger.exception("auto summary failed member=%s period=%s", member_id, period)
    return created


async def scheduler_loop(db_factory: async_sessionmaker, interval: int = CHECK_INTERVAL_SECONDS) -> None:
    """Background loop: periodically check for due periods and generate summaries."""
    while True:
        try:
            n = await run_due_summaries(db_factory)
            if n:
                logger.info("auto-generated %d periodic summary(ies)", n)
        except Exception:  # noqa: BLE001
            logger.exception("summary scheduler pass failed")
        await asyncio.sleep(interval)