"""Result collector for proactive agent (V1.4).

When a user replies to a proactive message, this module:
1. Detects if the user message is a reply to a proactive message
2. Extracts structured data from the reply via LLM
3. Updates the member's profile (metrics, tasks, etc.)
4. Handles "postpone" intent — reschedules the proactive reminder
5. Generates a natural follow-up message if needed
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyMember
from app.models.health import ChatMessage, MetricRecord
from app.models.tasks import HealthTask
from app.providers.base import Message
from app.providers.router import ModelRouter

logger = logging.getLogger(__name__)

RESULT_COLLECTION_PROMPT = """\
你是一个健康数据回收助手。用户刚回复了你的主动健康提醒，请根据用户回复提取结构化信息并判断后续操作。

你的职责：
1. 分析用户回复内容，提取结构化健康数据
2. 判断信息是否充分（是否需要追问）
3. 理解用户可能的"推迟"意图，重新安排提醒
4. 如果信息充分，输出结构化结果供系统更新画像
5. 如果信息不足，生成自然的追问消息

用户回复类型：
- 直接回答："降压药每天早上吃一颗" → 提取用药依从性
- 指标数值："刚量了血压145/90" → 提取指标数据
- 就诊反馈："去医院看了，医生说问题不大" → 提取就诊结果
- 推迟："这周忙，下周再去" → 理解推迟，重新安排
- 拒绝："不想去" → 标记 dismissed
- 已完成："已经看完了" → 标记完成

请严格按照以下 JSON 格式返回（不要包含 markdown 代码块标记）：
{
  "sufficient": true/false,
  "extracted_data": {
    "metrics": [
      {"metric_name": "指标标识符", "value": 数值, "unit": "单位"}
    ],
    "medication_update": "用药情况描述",
    "visit_outcome": "就诊结果描述",
    "new_diagnoses": ["新诊断"]
  },
  "followup_question": "如果信息不足，生成的追问消息",
  "task_action": {
    "action": "complete/dismiss/reschedule/none",
    "reschedule_days": 推迟天数,
    "reason": "推迟原因"
  },
  "new_tasks": [
    {"task_type": "medication/recheck/checkup/followup/custom", "title": "标题", "description": "描述"}
  ]
}

追问要求：
- 一次只追问一个问题
- 追问要自然，像聊天一样
- 连续两次回答含糊，不再追问，标记 sufficient=true

推迟理解：
- "明天去" → reschedule_days: 1
- "下周" → reschedule_days: 7
- "下周三" → 计算到下周三的天数
- "月底" → 计算到月底的天数
- "忙完这阵" → reschedule_days: 14
- "不想去" → action: dismiss
"""


async def find_last_proactive_message(
    db: AsyncSession, member_id: int
) -> ChatMessage | None:
    """Find the most recent proactive message that hasn't been collected yet."""
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.member_id == member_id,
            ChatMessage.source == "proactive",
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    msg = result.scalars().first()
    if msg is None:
        return None

    # Check if already collected (metadata has "collected": true)
    if msg.metadata_json:
        try:
            meta = json.loads(msg.metadata_json)
            if meta.get("collected"):
                return None
        except json.JSONDecodeError:
            pass

    return msg


async def collect_result(
    db: AsyncSession,
    router: ModelRouter,
    member_id: int,
    user_reply: str,
    proactive_msg: ChatMessage | None = None,
) -> dict[str, Any]:
    """Collect and process a user's reply to a proactive message.

    Returns:
        - sufficient: whether the reply contains enough info
        - followup: follow-up message to send (if insufficient)
        - task_action: task update action
        - metrics_saved: count of metrics extracted
    """
    if proactive_msg is None:
        proactive_msg = await find_last_proactive_message(db, member_id)

    if proactive_msg is None:
        return {"sufficient": True, "followup": None, "task_action": None, "metrics_saved": 0}

    # Build context for the LLM
    proactive_text = proactive_msg.content
    proactive_meta = {}
    if proactive_msg.metadata_json:
        try:
            proactive_meta = json.loads(proactive_msg.metadata_json)
        except json.JSONDecodeError:
            pass

    context = f"之前的主动提醒:\n{proactive_text}\n\n用户回复:\n{user_reply}"

    # Call LLM to extract structured data
    try:
        provider = router.get_text_provider()
        response = await provider.chat(
            [
                Message(role="system", content=RESULT_COLLECTION_PROMPT),
                Message(role="user", content=context),
            ],
            temperature=0.2,
            max_tokens=600,
        )
        raw = response.content.strip()

        # Parse JSON
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]
        if not raw.startswith("{"):
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Result collection LLM returned non-JSON: %s", raw[:200])
        return {"sufficient": True, "followup": None, "task_action": None, "metrics_saved": 0}
    except Exception:  # noqa: BLE001
        logger.exception("Result collection LLM call failed")
        return {"sufficient": True, "followup": None, "task_action": None, "metrics_saved": 0}

    metrics_saved = 0

    # Extract and save metrics
    extracted = result.get("extracted_data", {})
    metrics = extracted.get("metrics", [])
    for m in metrics:
        metric_name = m.get("metric_name")
        value = m.get("value")
        unit = m.get("unit", "")
        if metric_name and value is not None:
            try:
                val_float = float(value)
                record = MetricRecord(
                    member_id=member_id,
                    metric_name=metric_name,
                    value=val_float,
                    unit=unit,
                    measured_at=datetime.now(timezone.utc),
                )
                db.add(record)
                metrics_saved += 1
            except (ValueError, TypeError):
                logger.warning("Could not convert metric value %s to float", value)

    # Process task action
    task_action = result.get("task_action", {})
    action = task_action.get("action", "none")

    if action in ("complete", "dismiss", "reschedule"):
        # Find related tasks from proactive message metadata
        task_updates = proactive_meta.get("task_updates", [])
        patrol_id = proactive_meta.get("patrol_id", "")

        # Find tasks linked to this patrol
        if patrol_id:
            tasks = (
                await db.execute(
                    select(HealthTask).where(
                        HealthTask.member_id == member_id,
                        HealthTask.source_ref == f"patrol:{patrol_id}",
                        HealthTask.status == "open",
                    )
                )
            ).scalars().all()

            now = datetime.now(timezone.utc)
            for task in tasks:
                if action == "complete":
                    task.status = "done"
                    task.completed_at = now
                elif action == "dismiss":
                    task.status = "dismissed"
                    task.dismissed_at = now
                elif action == "reschedule":
                    days = task_action.get("reschedule_days", 7)
                    if task.due_date:
                        task.due_date = task.due_date + timedelta(days=days)
                    else:
                        task.due_date = date.today() + timedelta(days=days)

    # Create new tasks if specified
    for nt in result.get("new_tasks", []):
        from app.services.task_service import _add_task
        await _add_task(
            db=db,
            member_id=member_id,
            task_type=nt.get("task_type", "custom"),
            title=nt.get("title", ""),
            description=nt.get("description"),
            auto_generated=True,
        )

    # Mark proactive message as collected
    proactive_meta["collected"] = True
    proactive_meta["collection_result"] = {
        "sufficient": result.get("sufficient", True),
        "metrics_saved": metrics_saved,
        "task_action": task_action,
    }
    proactive_msg.metadata_json = json.dumps(proactive_meta, ensure_ascii=False)

    await db.commit()

    return {
        "sufficient": result.get("sufficient", True),
        "followup": result.get("followup_question"),
        "task_action": task_action,
        "metrics_saved": metrics_saved,
    }
