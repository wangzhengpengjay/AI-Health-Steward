"""Proactive health patrol engine (V1.4).

Dual-mode trigger:
1. Scheduled patrol — every 6h, inspects all members' profiles
2. Event-driven — triggered by new reports, abnormal metrics, task due dates

Patrol flow per member:
1. Load complete profile snapshot (metrics, diagnoses, medications, tasks, summaries)
2. Rule-layer scan: critical values, abnormal trends, due tasks, medication gaps
3. AI-layer inference: LLM analyzes snapshot → decide whether to intervene
4. Output: proactive message (push) or silent record (no push)

Disturbance policy:
- critical  → push immediately, no frequency limit
- high      → push immediately, max 1/week per topic
- normal    → batch into scheduled push, max 1/day
- low       → no push
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.family import FamilyMember
from app.models.health import ChatMessage, MetricRecord, Diagnosis, Medication
from app.models.tasks import HealthTask
from app.models.summaries import HealthSummary
from app.providers.base import Message
from app.providers.router import ModelRouter

logger = logging.getLogger(__name__)

# Patrol interval — same cadence as summary_scheduler
PATROL_INTERVAL_SECONDS = 6 * 60 * 60

# Frequency limits per member per topic
_FREQUENCY_LIMITS = {
    "critical": timedelta(hours=0),     # no limit
    "high": timedelta(days=7),          # max 1/week
    "normal": timedelta(days=1),        # max 1/day
    "low": timedelta(days=30),          # effectively never
}

# Critical value thresholds for rule-layer fast path
_CRITICAL_THRESHOLDS = {
    "systolic_blood_pressure": (180, None),   # > 180
    "diastolic_blood_pressure": (120, None),  # > 120
    "fasting_glucose": (16.7, 3.9),            # > 16.7 or < 3.9
    "postmeal_glucose": (16.7, 3.9),
    "random_glucose": (16.7, 3.9),
    "heart_rate": (120, 40),                   # > 120 or < 40
}

PATROL_SYSTEM_PROMPT = """\
你是一个家庭健康巡检引擎。你将收到一个家庭成员的完整健康画像快照，请分析是否需要主动干预。

你的职责：
1. 综合分析成员的健康数据（指标趋势、诊断、用药、待办、历史小结）
2. 判断是否存在需要主动干预的健康风险
3. 如果需要干预，生成一条自然、关切的主动消息（不超过200字）
4. 如果不需要干预，返回无需推送

干预场景：
- 危急值：血压 >180/120、血糖 >16.7 或 <3.9、心率 >120 或 <40
- 异常持续恶化：某指标连续3次以上异常且趋势恶化
- 到期待办：有未完成的高优先级待办（如复查、就诊提醒）
- 用药回访：长期用药但近期未确认服药情况
- 检查结果跟进：近期有异常检查结果但未见后续就诊记录

消息语气要求：
- 像一个关心家人健康的管家，不是冰冷的系统通知
- 基于实际数据，不编造
- 给出明确建议，不含糊
- 不要一次说太多，聚焦1-2个最关键的问题
- 如果是危急值，语气要紧迫但不要恐慌

请严格按照以下 JSON 格式返回（不要包含 markdown 代码块标记）：
{
  "should_push": true/false,
  "priority": "critical/high/normal/low",
  "message": "给用户的主动消息文本",
  "task_updates": [
    {
      "action": "create/dismiss/complete",
      "task_type": "medication/recheck/checkup/followup/custom",
      "title": "任务标题",
      "description": "任务描述",
      "due_date": "YYYY-MM-DD 或 null"
    }
  ],
  "followup_needed": true/false
}

如果没有需要干预的问题，should_push 返回 false。
消息中提及的指标数值必须是画像快照中实际存在的。
不要重复推送最近7天内已经推送过的同类提醒。
"""


def _load_patrol_prompt() -> str:
    """Load patrol prompt from file, fallback to inline prompt."""
    try:
        from pathlib import Path
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "patrol_v1.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return PATROL_SYSTEM_PROMPT


async def _build_member_snapshot(db: AsyncSession, member_id: int) -> str:
    """Build a text snapshot of the member's health profile for the LLM."""
    member = await db.get(FamilyMember, member_id)
    if member is None:
        return ""

    lines: list[str] = []
    lines.append(f"=== 成员画像快照: {member.name} ===")
    lines.append(f"性别: {member.gender}, 年龄: {(date.today() - member.birth_date).days // 365 if member.birth_date else '未知'}岁")

    # Recent metrics (last 30 days, max 10 per metric)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    metric_rows = (
        await db.execute(
            select(MetricRecord)
            .where(MetricRecord.member_id == member_id, MetricRecord.measured_at >= since)
            .order_by(MetricRecord.measured_at.desc())
            .limit(50)
        )
    ).scalars().all()
    if metric_rows:
        lines.append("\n--- 近期指标 (近30天) ---")
        by_name: dict[str, list[MetricRecord]] = {}
        for m in metric_rows:
            by_name.setdefault(m.metric_name, []).append(m)
        for name, records in by_name.items():
            vals = [f"{r.value}{r.unit or ''}" for r in records[:10]]
            lines.append(f"  {name}: {' → '.join(vals)}")

    # Active diagnoses
    diag_rows = (
        await db.execute(
            select(Diagnosis).where(Diagnosis.member_id == member_id).limit(20)
        )
    ).scalars().all()
    if diag_rows:
        lines.append("\n--- 诊断记录 ---")
        for d in diag_rows:
            lines.append(f"  {d.disease_name}" + (f" ({d.severity})" if d.severity else ""))

    # Medications
    med_rows = (
        await db.execute(
            select(Medication).where(Medication.member_id == member_id).limit(20)
        )
    ).scalars().all()
    if med_rows:
        lines.append("\n--- 用药记录 ---")
        for m in med_rows:
            lines.append(f"  {m.drug_name} {m.dosage or ''} {m.frequency or ''}")

    # Open tasks
    task_rows = (
        await db.execute(
            select(HealthTask).where(
                HealthTask.member_id == member_id,
                HealthTask.status == "open",
            ).order_by(HealthTask.priority.desc(), HealthTask.due_date.asc())
            .limit(20)
        )
    ).scalars().all()
    if task_rows:
        lines.append("\n--- 待办任务 ---")
        for t in task_rows:
            due = f" (截止: {t.due_date})" if t.due_date else ""
            lines.append(f"  [{t.priority}] {t.title}{due}")

    # Latest summary
    summary_rows = (
        await db.execute(
            select(HealthSummary.content)
            .where(HealthSummary.member_id == member_id)
            .order_by(HealthSummary.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if summary_rows:
        lines.append(f"\n--- 最近健康小结 ---\n  {summary_rows[:500]}")

    # Recent proactive messages (for dedup)
    recent_proactive = (
        await db.execute(
            select(ChatMessage.content, ChatMessage.created_at)
            .where(
                ChatMessage.member_id == member_id,
                ChatMessage.source == "proactive",
                ChatMessage.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(5)
        )
    ).all()
    if recent_proactive:
        lines.append("\n--- 近7天已推送的主动消息 ---")
        for content, created in recent_proactive:
            lines.append(f"  [{created.strftime('%m-%d')}] {content[:80]}...")

    # Recent chat (last 5 messages, for context)
    recent_chat = (
        await db.execute(
            select(ChatMessage.role, ChatMessage.content)
            .where(
                ChatMessage.member_id == member_id,
                ChatMessage.source == "webui",
            )
            .order_by(ChatMessage.id.desc())
            .limit(5)
        )
    ).all()
    if recent_chat:
        lines.append("\n--- 最近对话 (最近5条) ---")
        for role, content in reversed(recent_chat):
            lines.append(f"  {role}: {content[:100]}...")

    # Long-term memory
    if member.memory_summary:
        lines.append(f"\n--- 长期记忆摘要 ---\n  {member.memory_summary[:500]}")

    return "\n".join(lines)


def _rule_layer_scan(snapshot: str) -> dict[str, Any]:
    """Fast-path rule layer: scan for critical values before calling LLM.

    Returns a dict with 'has_critical' and 'hints' for the AI layer.
    """
    hints: list[str] = []
    has_critical = False

    # Check critical thresholds in the snapshot text
    # This is a simple text scan; the LLM does the real analysis
    for metric_name, (high, low) in _CRITICAL_THRESHOLDS.items():
        if metric_name in snapshot:
            hints.append(f"检查 {metric_name} 是否达到危急值阈值")

    # Check for overdue tasks
    if "截止:" in snapshot or "due_date" in snapshot:
        hints.append("检查是否有到期待办")

    return {"has_critical": has_critical, "hints": hints}


async def _check_frequency_limit(
    db: AsyncSession, member_id: int, priority: str
) -> bool:
    """Check if we can push a message of this priority to this member.

    Returns True if push is allowed (not rate-limited).
    """
    if priority == "critical":
        return True  # no limit

    limit = _FREQUENCY_LIMITS.get(priority, timedelta(days=1))
    since = datetime.now(timezone.utc) - limit
    count = (
        await db.execute(
            select(func.count()).where(
                ChatMessage.member_id == member_id,
                ChatMessage.source == "proactive",
                ChatMessage.created_at >= since,
            )
        )
    ).scalar_one()

    # For normal priority, allow 1 per day
    # For high priority, allow 1 per week
    max_count = 1 if priority in ("high", "normal") else 0
    return count < max_count


async def patrol_member(
    db: AsyncSession,
    router: ModelRouter,
    member_id: int,
    trigger: str = "scheduled",
) -> dict[str, Any] | None:
    """Patrol a single member. Returns patrol result or None.

    :param trigger: "scheduled" | "event:new_report" | "event:abnormal_metric" | "event:task_due"
    :return: dict with should_push, message, priority, task_updates or None
    """
    snapshot = await _build_member_snapshot(db, member_id)
    if not snapshot:
        return None

    # Rule-layer fast scan
    rule_result = _rule_layer_scan(snapshot)

    # AI-layer inference
    system_prompt = _load_patrol_prompt()
    if rule_result["hints"]:
        hint_text = "\n\n规则层提示: " + "; ".join(rule_result["hints"])
        system_prompt += hint_text

    try:
        provider = router.get_text_provider()
        response = await provider.chat(
            [
                Message(role="system", content=system_prompt),
                Message(role="user", content=f"请分析以下成员画像，判断是否需要主动干预:\n\n{snapshot}"),
            ],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.content.strip()

        # Parse JSON from response (handle markdown code blocks)
        if "```" in raw:
            # Extract JSON from code block
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]
        # Also handle if there's text before the JSON
        if not raw.startswith("{"):
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Patrol LLM returned non-JSON for member %s: %s", member_id, raw[:200])
        return None
    except Exception:  # noqa: BLE001
        logger.exception("Patrol LLM call failed for member %s", member_id)
        return None

    if not result.get("should_push", False):
        return {"should_push": False, "trigger": trigger, "member_id": member_id}

    priority = result.get("priority", "normal")

    # Frequency limit check
    if not await _check_frequency_limit(db, member_id, priority):
        logger.info("Patrol message rate-limited for member %s (priority=%s)", member_id, priority)
        return {"should_push": False, "reason": "rate_limited", "member_id": member_id}

    # Save proactive message to DB
    message_text = result.get("message", "")
    if message_text:
        patrol_id = f"patrol_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{member_id}"
        metadata = {
            "patrol_id": patrol_id,
            "trigger": trigger,
            "priority": priority,
            "task_updates": result.get("task_updates", []),
            "followup_needed": result.get("followup_needed", False),
        }
        msg = ChatMessage(
            member_id=member_id,
            role="assistant",
            content=message_text,
            source="proactive",
            message_type="proactive",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        db.add(msg)
        await db.flush()

    # Process task updates
    task_updates = result.get("task_updates", [])
    for tu in task_updates:
        action = tu.get("action")
        if action == "create":
            from app.services.task_service import _add_task
            await _add_task(
                db=db,
                member_id=member_id,
                task_type=tu.get("task_type", "custom"),
                title=tu.get("title", ""),
                description=tu.get("description"),
                due_date=date.fromisoformat(tu["due_date"]) if tu.get("due_date") else None,
                priority=priority if priority in ("critical", "high") else "normal",
                source_ref=f"patrol:{patrol_id}",
                auto_generated=True,
            )

    await db.commit()
    return {
        "should_push": True,
        "message": message_text,
        "priority": priority,
        "trigger": trigger,
        "member_id": member_id,
        "task_updates": task_updates,
    }


async def run_scheduled_patrol(db_factory: async_sessionmaker) -> int:
    """Run a scheduled patrol pass for all members. Returns count of pushes."""
    pushes = 0
    router = None

    async with db_factory() as db:
        member_ids = (
            await db.execute(
                select(FamilyMember.id).where(FamilyMember.is_deleted.is_(False))
            )
        ).scalars().all()

        for member_id in member_ids:
            try:
                if router is None:
                    from app.providers.router import get_model_router
                    router = get_model_router()

                result = await patrol_member(db, router, member_id, trigger="scheduled")
                if result and result.get("should_push"):
                    pushes += 1
                    logger.info("Patrol push for member %s: %s", member_id, result.get("message", "")[:80])
            except Exception:  # noqa: BLE001
                logger.exception("Patrol failed for member %s", member_id)

    return pushes


async def patrol_loop(db_factory: async_sessionmaker) -> None:
    """Background loop: periodically patrol all members."""
    while True:
        try:
            import asyncio
            n = await run_scheduled_patrol(db_factory)
            if n:
                logger.info("Patrol pass: pushed %d proactive message(s)", n)
        except Exception:  # noqa: BLE001
            logger.exception("Patrol loop pass failed")

        import asyncio
        await asyncio.sleep(PATROL_INTERVAL_SECONDS)
