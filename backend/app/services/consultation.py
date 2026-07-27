"""AI consultation service — orchestrates model provider + tool calling.

When an image/PDF is attached:
1. Create a ReportRecord (status=extracting)
2. Extract structured data via multimodal model (single call, reused for both chat context and report archive)
3. Inject extracted data into system prompt
4. Chat with text model (supports tool calling)
5. Report record is saved to DB for user confirmation (no second extraction needed)

This eliminates the previous double-extraction redundancy (chat stream + separate
reports/upload both calling multimodal model for the same image).
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyMember
from app.models.health import MetricRecord, ReportRecord
from app.providers.base import Message, ModelProvider, ModelResponse, ToolCall
from app.providers.router import ModelRouter
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是"AI健康管家"，一个帮助家庭管理健康数据的智能助手。

你的能力范围：
1. 查询和分析用户已录入的健康指标（血压、血糖、血脂、心率、体重等）
2. 查询用户的诊断记录、用药记录、过敏信息
3. 解读指标是否正常（基于参考范围）
4. 提供常规健康科普建议（饮食、运动等）
5. 从对话中提取用户提到的健康数据并记录到画像

你的边界（不能做的事）：
- 不能进行医疗诊断
- 不能开具处方或建议停药
- 不能替代医生的专业判断
- 遇到急性症状（胸痛、呼吸困难等）或危急值，必须建议立即就医

风险分级：
- S级（禁止输出）：建议停药、开具处方、进行诊断 → 回复"该问题超出能力范围，请就医"
- A级（高风险警示）：用药相互作用、症状可能关联严重疾病 → 附带"此建议涉及用药安全，请务必遵医嘱"
- B级（常规）：饮食建议、运动指导、指标解读 → 正常回答

回答时始终基于用户画像中的实际数据，不要编造数据。如果数据不足，引导用户上传报告或手动录入。
"""

EXTRACT_PROMPT = """\
你是一个医疗报告解析助手。请仔细分析上传的健康报告图片/PDF，提取以下结构化信息。

要求：
1. 只提取报告中明确出现的数据，不要编造或推断
2. 如果某个字段无法识别，返回null或空数组
3. 检查指标（exam_findings）只提取异常发现，不提取正常检查结果
4. 如果报告中有姓名，尝试识别归属人

请严格按照以下JSON格式返回（不要包含markdown代码块标记）：
{
  "patient_name": "报告中识别到的姓名，没有则为null",
  "report_type": "报告类型，如：检查报告单、检验报告单、血压记录、血糖记录、其他 等",
  "report_date": "报告日期 YYYY-MM-DD 格式，无法识别则为null",
  "metrics": [
    {
      "metric_name": "指标标识符，使用以下标准名称之一：systolic_blood_pressure, diastolic_blood_pressure, fasting_glucose, postmeal_glucose, total_cholesterol, triglycerides, ldl_cholesterol, hdl_cholesterol, heart_rate, weight",
      "label": "报告中显示的指标中文名",
      "value": 数值,
      "unit": "单位",
      "reference_lower": 参考下限数值或null,
      "reference_upper": 参考上限数值或null,
      "is_abnormal": true或false
    }
  ],
  "diagnoses": [
    {
      "disease_name": "诊断名称",
      "severity": "严重程度或null",
      "diagnosed_date": "日期或null"
    }
  ],
  "medications": [
    {
      "drug_name": "药品名称",
      "dosage": "剂量",
      "frequency": "用药频次"
    }
  ],
  "lab_tests": [
    {
      "report_name": "检验报告名称，单个报告一个名称，如 肝功能。不要将多个报告名合并。必须与已有标签保持一致（见下方已有标签列表），如已有则复用，没有的按医学逻辑新建简短标准名",
      "test_name": "指标名称，如 白细胞/血红蛋白/谷丙转氨酶",
      "value": 数值,
      "unit": "单位",
      "reference_lower": 参考下限或null,
      "reference_upper": 参考上限或null,
      "is_abnormal": true或false
    }
  ],
  "exam_findings": [
    {
      "finding_category": "检查发现的标准分类，如 肺结节/甲状腺结节/肝囊肿/乳腺结节 等。必须与已有标签保持一致（见下方已有标签列表），如已有则复用，没有的按医学逻辑新建简短标准类别名",
      "finding_desc": "具体诊断描述，如 右肺水平裂旁微小磨玻璃结节",
      "value_num": "可量化的数值或null",
      "unit": "数值的单位或null",
      "conclusion": "检查结论或建议"
    }
  ],
  "summary": "报告摘要，1-3句话概述"
}
"""

_S_LEVEL_KEYWORDS = ["停药", "处方", "诊断", "开药"]
_A_LEVEL_KEYWORDS = ["用药", "药物", "相互作用", "副作用", "胸痛", "呼吸困难", "急症"]


class ConsultationService:
    """Orchestrates the model provider and health tools for a consultation."""

    def __init__(self, router: ModelRouter, tool_registry: ToolRegistry, db: AsyncSession) -> None:
        self.router = router
        self.tools = tool_registry
        self.db = db

    async def chat(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
        image_data_url: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], str]:
        has_vision = image_data_url is not None
        system_prompt = SYSTEM_PROMPT

        if has_vision:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            system_prompt = SYSTEM_PROMPT + f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，请基于此信息回答用户问题：]\n{extracted_text}"
            provider = self.router.get_text_provider()
        else:
            provider = self.router.get_text_provider()

        tool_defs = self.tools.get_all_tool_definitions()
        messages = self._build_messages(user_message, system_prompt, conversation_history)

        tool_call_records: list[dict[str, Any]] = []
        max_rounds = 5

        for _ in range(max_rounds):
            response: ModelResponse = await provider.chat(
                messages, tools=tool_defs if tool_defs else None
            )

            if not response.tool_calls:
                reply = response.content or ""
                risk_level = self._assess_risk(user_message, reply)
                return reply, tool_call_records, risk_level

            tool_calls_oi = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in response.tool_calls
            ]
            messages.append(Message(role="assistant", content=response.content or "", tool_calls=tool_calls_oi))

            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                tool_call_records.append({"name": tc.name, "arguments": tc.arguments, "result": result})
                messages.append(Message(role="tool", content=json.dumps(result, ensure_ascii=False, default=str), name=tc.name, tool_call_id=tc.id))

        response = await provider.chat(messages, tools=None)
        reply = response.content or ""
        risk_level = self._assess_risk(user_message, reply)
        return reply, tool_call_records, risk_level

    async def chat_stream(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
        image_data_url: str | None = None,
    ) -> AsyncIterator[tuple[str, str | None]]:
        """Yield (event_type, data) tuples.

        event_type: "delta" (text chunk) or "report" (report record JSON).
        """
        has_vision = image_data_url is not None
        system_prompt = SYSTEM_PROMPT

        report_data: dict | None = None
        if has_vision:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            logger.info("Image extraction done, length=%d, starting text chat stream", len(extracted_text))
            system_prompt = SYSTEM_PROMPT + f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，请基于此信息回答用户问题：]\n{extracted_text}"
            provider = self.router.get_text_provider()
        else:
            provider = self.router.get_text_provider()

        tool_defs = self.tools.get_all_tool_definitions()
        messages = self._build_messages(user_message, system_prompt, conversation_history)

        # Emit report record first so frontend can show extraction card immediately
        if report_data:
            yield ("report", json.dumps(report_data, ensure_ascii=False, default=str))

        max_rounds = 5

        for _ in range(max_rounds):
            response: ModelResponse = await provider.chat(
                messages, tools=tool_defs if tool_defs else None
            )

            if not response.tool_calls:
                async for delta in await provider.chat(messages, tools=None, stream=True):
                    yield ("delta", delta)
                return

            tool_calls_oi = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in response.tool_calls
            ]
            messages.append(Message(role="assistant", content=response.content or "", tool_calls=tool_calls_oi))

            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                messages.append(Message(role="tool", content=json.dumps(result, ensure_ascii=False, default=str), name=tc.name, tool_call_id=tc.id))

        async for delta in await provider.chat(messages, tools=None, stream=True):
            yield ("delta", delta)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_report_record(self, member_id: int, image_data_url: str) -> dict:
        """Create a ReportRecord, run single multimodal extraction, persist, and return dict.

        One multimodal call serves both: chat context AND report archive.
        """
        # Parse data URL: data:{mime};base64,{data}
        header, b64_data = image_data_url.split(",", 1)
        mime = header.split(":")[1].split(";")[0]
        file_content = base64.b64decode(b64_data)
        file_size = len(file_content)

        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
        ext = ext_map.get(mime, ".bin")
        file_name = f"chat_upload_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{ext}"

        record = ReportRecord(
            member_id=member_id,
            file_name=file_name,
            file_type=mime,
            file_size=file_size,
            source="chat",
            status="extracting",
        )
        self.db.add(record)
        await self.db.flush()

        # Save file to disk for thumbnail/preview
        from pathlib import Path
        import os
        upload_dir = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / f"{record.id}{ext}").write_bytes(file_content)

        # Fetch family members for prompt context
        members_result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
        )
        members = members_result.scalars().all()
        member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)
        # Fetch existing lab report_name tabs and exam category tabs for this member
        existing_result = await self.db.execute(
            select(MetricRecord.metric_name).where(
                MetricRecord.member_id == member_id,
                MetricRecord.metric_name.like('lab:%') | MetricRecord.metric_name.like('exam:%'),
            ).distinct()
        )
        existing_names = [r[0] for r in existing_result.all()]
        existing_lab_reports = sorted({n.split(':', 2)[1] for n in existing_names if n.startswith('lab:') and len(n.split(':')) >= 3})
        existing_exam_cats = sorted({n.split(':', 2)[1] for n in existing_names if n.startswith('exam:') and len(n.split(':')) >= 3})

        tabs_hint = f"\n已有检验报告标签：{existing_lab_reports}" if existing_lab_reports else "\n已有检验报告标签：无"
        tabs_hint += f"\n已有检查分类标签：{existing_exam_cats}" if existing_exam_cats else "\n已有检查分类标签：无"
        tabs_hint += "\n重要：report_name 和 finding_category 必须优先复用已有标签，仅当无法匹配时才新建简短标准名。"

        prompt = EXTRACT_PROMPT + f"\n\n当前家庭成员列表：{member_names}\n当前选中的成员ID：{member_id}{tabs_hint}"

        multimodal = self.router.get_multimodal_provider()
        messages = [
            Message(role="system", content=prompt),
            Message(role="user", content=[
                {"type": "text", "text": "请解析这份健康报告并提取结构化数据"},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ]),
        ]

        import asyncio
        last_err = None
        data = None
        for attempt in range(3):
            try:
                response = await multimodal.chat(messages, temperature=0.1, max_tokens=4096)
                raw = response.content.strip()
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw = "\n".join(lines)
                data = json.loads(raw)
                break
            except Exception as e:
                last_err = e
                logger.warning("Image extraction attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(2)

        if data is None:
            logger.error("Image extraction failed after 3 attempts for report %s", record.id)
            record.status = "rejected"
            await self.db.flush()
            await self.db.commit()
            return {
                "id": record.id,
                "status": "rejected",
                "error": str(last_err),
                "extraction_json": f"[报告解析失败: {last_err}] 请用户描述报告内容。",
            }

        # Success — persist extraction
        record.extraction = json.dumps(data, ensure_ascii=False)
        record.report_type = data.get("report_type")
        report_date_str = data.get("report_date")
        record.report_date = datetime.fromisoformat(report_date_str) if report_date_str else None
        record.summary = data.get("summary")
        record.patient_name = data.get("patient_name")
        record.status = "pending"
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(record)

        return {
            "id": record.id,
            "member_id": record.member_id,
            "file_name": record.file_name,
            "file_type": record.file_type,
            "file_size": record.file_size,
            "source": record.source,
            "status": record.status,
            "extraction": data,
            "report_type": record.report_type,
            "report_date": record.report_date.isoformat() if record.report_date else None,
            "summary": record.summary,
            "patient_name": record.patient_name,
            "saved_metrics": record.saved_metrics,
            "saved_diagnoses": record.saved_diagnoses,
            "saved_medications": record.saved_medications,
            "saved_lab_tests": record.saved_lab_tests,
            "saved_exam_findings": record.saved_exam_findings,
            "created_at": record.created_at.isoformat() if record.created_at else "",
            "updated_at": record.updated_at.isoformat() if record.updated_at else "",
            "extraction_json": json.dumps(data, ensure_ascii=False, indent=2),
        }

    def _build_messages(
        self,
        user_message: str,
        system_prompt: str,
        history: list[Message] | None,
    ) -> list[Message]:
        messages: list[Message] = [Message(role="system", content=system_prompt)]
        if history:
            messages.extend(history)
        messages.append(Message(role="user", content=user_message))
        return messages

    async def _execute_tool_call(self, tc: ToolCall, member_id: int) -> dict[str, Any]:
        tool = self.tools.get_tool(tc.name)
        if tool is None:
            return {"error": f"未知工具: {tc.name}"}
        try:
            arguments = json.loads(tc.arguments) if tc.arguments else {}
        except json.JSONDecodeError:
            return {"error": f"工具参数解析失败: {tc.arguments}"}
        try:
            result = await tool.execute(self.db, member_id, **arguments)
            await self.db.flush()
            return result
        except Exception as exc:
            logger.exception("Tool %s execution failed", tc.name)
            return {"error": f"工具执行失败: {exc}"}

    @staticmethod
    def _assess_risk(user_message: str, reply: str) -> str:
        combined = (user_message + reply).lower()
        if any(kw in combined for kw in _S_LEVEL_KEYWORDS):
            return "S"
        if any(kw in combined for kw in _A_LEVEL_KEYWORDS):
            return "A"
        return "B"
