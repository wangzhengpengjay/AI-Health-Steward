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
from app.models.health import ChatMessage, MetricRecord, ReportRecord
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

重要规则 — 数据提取优先：
当用户在对话中提到自己的健康指标数值（如"我血压180/90"、"空腹血糖6.5"等），你必须：
1. 立即调用 extract_and_save 工具将提到的指标保存到画像
2. 血压需要分别提取收缩压(systolic_blood_pressure)和舒张压(diastolic_blood_pressure)两条记录
3. 保存后再基于该数据进行分析和回复
4. 在回复中告知用户数据已记录
不要只回复建议而遗漏数据记录。

重要规则 — 风险自测量表：
当用户表现出与量表相关的筛查需求或风险信号时，主动调用 assess_scale 工具提供相应量表：
- 提到"糖尿病/血糖高/多饮多尿/体重下降/想吃甜" → 推荐 diabetes 糖尿病风险自测
- 提到"心血管/冠心病/心梗/脑梗/血脂高/血压高/心慌/胸闷" → 推荐 ascvd 心血管风险自测
- 提到"情绪低落/抑郁/没兴趣/沮丧/想不开/睡不着" → 推荐 phq9 抑郁自评（PHQ-9）
- 提到"焦虑/紧张/担心/害怕/心慌/不安/压力大/烦躁" → 推荐 gad7 焦虑自评（GAD-7）
调用方式：
1. 先调用 assess_scale(scale_code=...)（不带 answers），获得题目后向用户逐一提问
2. 用户作答后，将答案以 {question_id: 分值} 形式传入 assess_scale(scale_code=..., answers=...) 进行计分
3. 根据返回的 risk_level 给出解读与建议，并附上量表免责声明（自筛参考，不能替代专业诊断）
不要在同一轮里一次性索要全部量表，一次只推荐与当前话题最相关的一个。
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
      "value": 数值或文本（定性结果如"淡黄色"、"透明"用文本，定量结果用数值）,
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
      "value": 数值或文本（定性结果如"淡黄色"、"透明"用文本，定量结果用数值）,
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
        source: str = "webui",
    ) -> tuple[str, list[dict[str, Any]], str]:
        has_vision = image_data_url is not None
        system_prompt = await self._build_system_prompt(member_id, source)

        if conversation_history is None:
            conversation_history = await self._load_recent_history(member_id, source)
        await self._save_message(member_id, "user", user_message, source)

        if has_vision:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            system_prompt = system_prompt + f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，请基于此信息回答用户问题：]\n{extracted_text}"
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
                await self._save_message(member_id, "assistant", reply, source)
                await self._after_turn(member_id, source)
                return reply, tool_call_records, risk_level

            tool_calls_oi = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in response.tool_calls
            ]
            messages.append(Message(role="assistant", content=response.content or "", tool_calls=tool_calls_oi))

            self._align_bp_measured_at(response.tool_calls)
            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                tool_call_records.append({"name": tc.name, "arguments": tc.arguments, "result": result})
                messages.append(Message(role="tool", content=json.dumps(result, ensure_ascii=False, default=str), name=tc.name, tool_call_id=tc.id))

        response = await provider.chat(messages, tools=None)
        reply = response.content or ""
        risk_level = self._assess_risk(user_message, reply)
        await self._save_message(member_id, "assistant", reply, source)
        await self._after_turn(member_id, source)
        return reply, tool_call_records, risk_level

    async def chat_stream(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
        image_data_url: str | None = None,
        source: str = "webui",
    ) -> AsyncIterator[tuple[str, str | None]]:
        """Yield (event_type, data) tuples.

        event_type: "delta" (text chunk) or "report" (report record JSON).
        """
        has_vision = image_data_url is not None
        system_prompt = await self._build_system_prompt(member_id, source)

        if conversation_history is None:
            conversation_history = await self._load_recent_history(member_id, source)
        await self._save_message(member_id, "user", user_message, source)

        report_data: dict | None = None
        if has_vision:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            logger.info("Image extraction done, length=%d, starting text chat stream", len(extracted_text))
            system_prompt = system_prompt + f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，请基于此信息回答用户问题：]\n{extracted_text}"
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
                full_reply: list[str] = []
                async for delta in await provider.chat(messages, tools=None, stream=True):
                    full_reply.append(delta)
                    yield ("delta", delta)
                await self._save_message(member_id, "assistant", "".join(full_reply), source)
                await self._after_turn(member_id, source)
                return

            tool_calls_oi = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in response.tool_calls
            ]
            messages.append(Message(role="assistant", content=response.content or "", tool_calls=tool_calls_oi))

            self._align_bp_measured_at(response.tool_calls)
            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                messages.append(Message(role="tool", content=json.dumps(result, ensure_ascii=False, default=str), name=tc.name, tool_call_id=tc.id))

        full_reply: list[str] = []
        async for delta in await provider.chat(messages, tools=None, stream=True):
            full_reply.append(delta)
            yield ("delta", delta)
        await self._save_message(member_id, "assistant", "".join(full_reply), source)
        await self._after_turn(member_id, source)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_system_prompt(self, member_id: int, source: str = "webui") -> str:
        """Build the system prompt, injecting long-term memory if present (P1-4)."""
        from app.services.member_memory import get_memory_summary

        prompt = SYSTEM_PROMPT
        memory = await get_memory_summary(self.db, member_id)
        if memory:
            prompt += (
                "\n\n[长期记忆 — 这是该成员此前的健康咨询要点，供你参考，帮助记住TA的病情、"
                "用药、偏好与待跟进事项。若与本次问题无关可忽略，但不要与已有数据矛盾：]\n"
                + memory
            )
        return prompt

    async def _after_turn(self, member_id: int, source: str = "webui") -> None:
        """Post-turn hook: compact recent messages into long-term memory (P1-4)."""
        try:
            from app.services.member_memory import maybe_compact_memory

            await maybe_compact_memory(self.db, self.router, member_id, source)
            await self.db.flush()
        except Exception:  # noqa: BLE001
            logger.exception("Post-turn memory compaction raised for member %s", member_id)

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
        from app.services.image_utils import prepare_for_multimodal
        data_urls = prepare_for_multimodal(file_content, mime)
        user_content: list[dict] = [{"type": "text", "text": "请解析这份健康报告并提取结构化数据"}]
        for url in data_urls:
            user_content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [
            Message(role="system", content=prompt),
            Message(role="user", content=user_content),
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

    async def _load_recent_history(self, member_id: int, source: str = "webui") -> list[Message]:
        """Load the member's persisted webui history as LLM context.

        The webui is a single continuous conversation stream per member. We load the
        most recent 50 messages (capped) so the model can continue the previous
        conversation across sessions, not just the last 30 minutes.
        """
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.member_id == member_id, ChatMessage.source == "webui")
            .order_by(ChatMessage.id.desc())
            .limit(50)
        )
        rows = list(result.scalars().all())
        rows.reverse()  # back to ascending order for the context window
        return [Message(role=r.role, content=r.content) for r in rows]

    async def _save_message(self, member_id: int, role: str, content: str, source: str = "webui") -> None:
        """Persist a chat message for future history."""
        self.db.add(ChatMessage(member_id=member_id, role=role, content=content, source=source))
        await self.db.flush()

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

    BP_METRICS = ("systolic_blood_pressure", "diastolic_blood_pressure")

    @staticmethod
    def _align_bp_measured_at(tool_calls: list[ToolCall] | None) -> list[ToolCall] | None:
        """同一轮工具调用中若同时提取收缩压+舒张压，强制两者使用同一个 measured_at。

        血压作为两条独立 MetricRecord(收缩压/舒张压)存储，前端按 measured_at 精确配对合并展示。
        若模型生成的两次提取时间戳不一致，会把同一组血压拆成两条残缺记录(如"收缩压 -- / 舒张压 90")。
        此方法在保存前把同轮收缩压/舒张压的 measured_at 对齐为同一确定值，从源头防呆。
        """
        if not tool_calls:
            return tool_calls

        bp_calls: list[ToolCall] = []
        for tc in tool_calls:
            if tc.name != "extract_and_save":
                continue
            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                continue
            if args.get("data_type") != "metric":
                continue
            if args.get("metric_name") in ConsultationService.BP_METRICS:
                bp_calls.append(tc)

        # 仅当同轮同时覆盖收缩压和舒张压时才需要对齐
        names = {json.loads(tc.arguments).get("metric_name") for tc in bp_calls}
        if not {"systolic_blood_pressure", "diastolic_blood_pressure"}.issubset(names):
            return tool_calls

        # 统一时间戳：优先用已给的合法测量时间，否则用当前时间
        unified = None
        for tc in bp_calls:
            args = json.loads(tc.arguments)
            if args.get("measured_at"):
                unified = args["measured_at"]
                break
        if unified is None:
            unified = datetime.now(timezone.utc).isoformat()

        for tc in bp_calls:
            args = json.loads(tc.arguments)
            args["measured_at"] = unified
            tc.arguments = json.dumps(args, ensure_ascii=False)
        return tool_calls

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
            # 工具执行是真实的状态变更(保存指标/症状/用药/待办), 必须立即提交持久化.
            # 非流式 /chat 依赖请求尾部的 get_db.commit() 能落库, 但 SSE 流式 /chat/stream 的
            # event_generator 在 StreamingResponse 里用 session, 依赖清理时的 commit 不可靠,
            # 会导致工具保存的数据被回滚丢弃. 因此在工具执行后显式提交.
            await self.db.commit()
            return result
        except Exception as exc:
            await self.db.rollback()
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
