"""Health task service — generate and query actionable to-dos for family members.

Tasks are auto-generated from health events (critical/abnormal metrics,
medications, chronic diagnoses, checkup recommendations) and can also be
managed manually by the user.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import metric_label as _metric_label
from app.models.tasks import HealthTask

logger = logging.getLogger(__name__)

# Priority for auto-generated task types
_TASK_DEFAULTS: dict[str, dict[str, Any]] = {
    "medication": {"priority": "normal"},
    "recheck": {"priority": "normal"},
    "checkup": {"priority": "normal"},
    "vaccination": {"priority": "normal"},
    "followup": {"priority": "normal"},
}


async def _add_task(
    db: AsyncSession,
    member_id: int,
    task_type: str,
    title: str,
    description: str | None = None,
    due_date: date | None = None,
    priority: str = "normal",
    source_ref: str | None = None,
    auto_generated: bool = True,
) -> HealthTask | None:
    """Insert a task, de-duplicating against an equivalent open task.

    Dedup uses the stable natural key (member, task_type, title, status=open)
    rather than ``source_ref`` alone. ``source_ref`` embeds a per-row id for
    metrics (``metric:{id}``) and checkups (``checkup:{id}``), so it is unique
    by construction and the old dedup never fired: three critical systolic
    readings produced three identical "尽快复查收缩压" to-dos, and each checkup
    recommendation added another identical appointment task.

    When an equivalent open task exists it is refreshed (most urgent priority,
    earliest due date) instead of duplicated.
    """
    existing = (
        await db.execute(
            select(HealthTask).where(
                HealthTask.member_id == member_id,
                HealthTask.task_type == task_type,
                HealthTask.title == title,
                HealthTask.status == "open",
            )
        )
    ).scalars().first()
    if existing is not None:
        if priority == "critical":
            existing.priority = "critical"
        if due_date is not None and (
            existing.due_date is None or due_date < existing.due_date
        ):
            existing.due_date = due_date
        await db.flush()
        return None
    task = HealthTask(
        member_id=member_id,
        task_type=task_type,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        status="open",
        source_ref=source_ref,
        auto_generated=auto_generated,
    )
    db.add(task)
    await db.flush()
    return task



# ---------------------------------------------------------------------------
# Event hooks — called from metric / medication / diagnosis / checkup flows
# ---------------------------------------------------------------------------

async def handle_metric_recorded(
    db: AsyncSession,
    member_id: int,
    metric_name: str,
    is_abnormal: bool,
    is_critical: bool,
    record_id: int,
) -> HealthTask | None:
    """Generate a task after a metric is saved.

    Only CRITICAL values get an immediate to-do (seek care / re-test today).
    Abnormal-but-not-critical rechecks are delegated to the summary-time model
    judgment (`_sync_recheck_tasks`), which groups by check category and
    calibrates the due date — avoiding duplicate to-dos from dual sources.
    """
    if is_critical:
        return await _add_task(
            db,
            member_id,
            "recheck",
            f"尽快复查{_metric_label(metric_name)}",
            description="检测到危急值，请尽快就医或复测确认。",
            due_date=date.today(),
            priority="critical",
            source_ref=f"metric:{record_id}",
        )
    return None


async def handle_medication_added(
    db: AsyncSession,
    member_id: int,
    drug_name: str,
    medication_id: int,
    end_date: date | None,
) -> HealthTask | None:
    """Generate a medication reminder if the drug is ongoing (no end date)."""
    if end_date:
        return None
    return await _add_task(
        db,
        member_id,
        "medication",
        f"按时服用/续配：{drug_name}",
        description="该用药正在使用，请按时服用，注意备药。",
        due_date=None,
        priority="normal",
        source_ref=f"med:{medication_id}",
    )


async def handle_diagnosis_added(
    db: AsyncSession,
    member_id: int,
    disease_name: str,
    diagnosis_id: int,
    status: str,
) -> HealthTask | None:
    """Generate a chronic follow-up reminder for active diagnoses."""
    if status != "active":
        return None
    return await _add_task(
        db,
        member_id,
        "followup",
        f"{disease_name} 定期随访",
        description="该慢性病处于管理期，建议按医嘱定期随访复查。",
        due_date=date.today() + timedelta(days=90),
        priority="normal",
        source_ref=f"diagnosis:{diagnosis_id}",
    )


async def handle_checkup_generated(
    db: AsyncSession,
    member_id: int,
    title: str,
    checkup_id: int,
) -> HealthTask | None:
    """Generate a checkup appointment task after a recommendation is produced."""
    return await _add_task(
        db,
        member_id,
        "checkup",
        title,
        description="根据体检推荐，建议预约该项检查。",
        due_date=date.today() + timedelta(days=90),
        priority="normal",
        source_ref=f"checkup:{checkup_id}",
    )


# ---------------------------------------------------------------------------
# Query / management
# ---------------------------------------------------------------------------

async def list_tasks(
    db: AsyncSession,
    member_id: int,
    status: str = "open",
    task_type: str | None = None,
) -> list[HealthTask]:
    stmt = (
        select(HealthTask)
        .where(HealthTask.member_id == member_id)
        .order_by(
            HealthTask.status.asc(),
            # `priority` is a text column, so a plain .desc() sorted
            # alphabetically ("normal" > "low" > "high" > "critical") and pushed
            # the most urgent items to the bottom of the list. Map to an
            # explicit severity weight instead.
            _priority_weight().asc(),
            HealthTask.due_date.asc().nulls_last(),
        )
    )
    if status == "open":
        stmt = stmt.where(HealthTask.status == "open")
    elif status == "all":
        pass
    else:
        stmt = stmt.where(HealthTask.status == status)
    if task_type:
        stmt = stmt.where(HealthTask.task_type == task_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# Severity weight: lower sorts first. Keep in sync with the frontend's
# TaskPriority union ('critical' | 'high' | 'normal' | 'low').
_PRIORITY_WEIGHTS = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def _priority_weight():
    return case(
        *[(HealthTask.priority == name, weight) for name, weight in _PRIORITY_WEIGHTS.items()],
        else_=len(_PRIORITY_WEIGHTS),
    )



async def overview(
    db: AsyncSession,
    member_ids: list[int],
) -> list[dict[str, Any]]:
    """Family-level overview: open + overdue counts per member."""
    if not member_ids:
        return []
    result = await db.execute(
        select(HealthTask)
        .where(
            HealthTask.member_id.in_(member_ids),
            HealthTask.status == "open",
        )
    )
    tasks = list(result.scalars().all())
    today = date.today()
    by_member: dict[int, dict[str, Any]] = {}
    for t in tasks:
        d = by_member.setdefault(t.member_id, {"member_id": t.member_id, "open": 0, "overdue": 0, "critical": 0})
        d["open"] += 1
        if t.due_date is not None and t.due_date < today:
            d["overdue"] += 1
        if t.priority == "critical":
            d["critical"] += 1
    return [by_member[mid] for mid in member_ids if mid in by_member]


async def complete_task(db: AsyncSession, task_id: int) -> HealthTask | None:
    task = await db.get(HealthTask, task_id)
    if task is None or task.status != "open":
        return task
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return task


async def dismiss_task(db: AsyncSession, task_id: int) -> HealthTask | None:
    task = await db.get(HealthTask, task_id)
    if task is None or task.status != "open":
        return task
    task.status = "dismissed"
    task.dismissed_at = datetime.now(timezone.utc)
    await db.flush()
    return task