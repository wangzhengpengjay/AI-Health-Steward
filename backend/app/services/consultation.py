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
from app.prompts import EXTRACT_PROMPT
from app.providers.base import Message, ModelProvider, ModelResponse, ToolCall
from app.providers.router import ModelRouter
from app.services.extraction_rules import normalize_extraction
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
涉及既往史、生活方式（吸烟/饮酒等）、用药、过敏、家族史、手术史、疫苗史等问题时，若画像信息不完整，请先调用 query_profile 工具按需查询后再回答；不要仅凭猜测回答"不知道"。

重要规则 — 数据提取优先：
当用户在对话中提到自己的健康指标数值（如"我血压180/90"、"空腹血糖6.5"等），你必须：
1. 立即调用 extract_and_save 工具将提到的指标保存到画像
2. 血压需要分别提取收缩压(systolic_blood_pressure)和舒张压(diastolic_blood_pressure)两条记录
3. 血糖必须使用标准标识：空腹 fasting_glucose、餐后1h postmeal_1h_glucose、餐后2h postmeal_glucose、睡前 bedtime_glucose。用户说"餐后2h血糖/餐后血糖"一律用 postmeal_glucose；用户只说"血糖"且未明确餐前/餐后/睡前状态时，一律用 random_glucose
4. 保存后再基于该数据进行分析和回复
5. 在回复中告知用户数据已记录
6. 用户以"我...是X"的句式给出新测量值时，一律视为新测量，必须先调用工具落库；不能仅凭历史记录声称"已记录"而跳过工具调用。只有用户明确是在询问或确认旧值时，才不重复保存
不要只回复建议而遗漏数据记录。

提取边界（务必遵守，避免重复污染）：
- 只提取用户【本次消息】中新给出的测量值。对话历史里已经记录过、或回复中为了对比趋势而引用的旧值，一律【不要】再次调用 extract_and_save。
- 例如用户本次只发"我血压152.99"，则只提取 152/99 这一组（收缩压152、舒张压99），绝不把历史上 140/90、145/98、149/99 等旧值当作本次提取目标。
- 若用户只给一个血压数字（如"血压152.99"），推断为"收缩压/舒张压"形式：前面为收缩压，后面为舒张压。
- 同一时间戳只允许存在一组血压记录；历史多组测量值应保持各自原有的 measured_at，不要统一成当前时间。
- 不确定是否新值时，优先少提取（宁缺毋滥），避免重复记录。

重要规则 — 风险自测量表：
当用户表现出与量表相关的筛查需求或风险信号时，主动调用 assess_scale 工具提供相应量表：
- 提到"糖尿病/血糖高/多饮多尿/体重下降/想吃甜" → 推荐 diabetes 糖尿病风险自测
- 提到"心血管/冠心病/心梗/脑梗/血脂高/血压高/心慌/胸闷" → 推荐 ascvd 心血管风险自测
- 提到“情绪低落/抑郁/没兴趣/沮丧/想不开” → 推荐 phq9 抑郁自评（PHQ-9）
- 提到“焦虑/紧张/担心/害怕/心慌/不安/压力大/烦躁” → 推荐 gad7 焦虑自评（GAD-7）
- 提到“失眠/睡不着/入睡难/早醒/多梦/睡不好” → 推荐 isi 失眠严重指数（ISI）
- 提到“高血压/血压高/头晕/盐吃多/家族高血压” → 推荐 hypertension 高血压风险自测
- 提到“血脂高/胆固醇高/甘油三酯/血脂异常” → 推荐 dyslipidemia 血脂异常风险自测
- 提到“记性差/忘事/认知/痴漏/老糊涂/重复问” → 推荐 ad8 认知障碍早期筛查（AD8）
- 提到“卒中/中风/脑梗/面瘫/言语不清/肢体麻木” → 推荐 stroke 脑卒中风险自测
调用方式：
1. 先调用 assess_scale(scale_code=...)（不带 answers），获得题目后向用户逐一提问
2. 用户作答后，将答案以 {question_id: 分值} 形式传入 assess_scale(scale_code=..., answers=...) 进行计分
3. 根据返回的 risk_level 给出解读与建议，并附上量表免责声明（自筛参考，不能替代专业诊断）
不要在同一轮里一次性索要全部量表，一次只推荐与当前话题最相关的一个。
"""

_S_LEVEL_KEYWORDS = ["停药", "处方", "诊断", "开药"]
_A_LEVEL_KEYWORDS = ["用药", "药物", "相互作用", "副作用", "胸痛", "呼吸困难", "急症"]


class ConsultationService:
    """Orchestrates the model provider and health tools for a consultation."""

    def __init__(self, router: ModelRouter, tool_registry: ToolRegistry, db: AsyncSession) -> None:
        self.router = router
        self.tools = tool_registry
        self.db = db

    async def _prepare_turn(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None,
        image_data_url: str | None,
        source: str,
    ) -> tuple[list[Message], list[dict[str, Any]], ModelProvider]:
        """Common setup for chat() and chat_stream().

        Returns (messages, tool_defs, provider) ready for the model call loop.
        Handles: system prompt, history, user message persistence, image extraction.
        """
        system_prompt = await self._build_system_prompt(member_id, source)

        if conversation_history is None:
            conversation_history = await self._load_recent_history(member_id, source)
        await self._save_message(member_id, "user", user_message, source)

        if image_data_url is not None:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            logger.info("Image extraction done, length=%d", len(extracted_text))
            system_prompt += (
                f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，"
                f"请基于此信息回答用户问题：]\n{extracted_text}"
            )

        provider = self.router.get_text_provider()
        tool_defs = self.tools.get_all_tool_definitions()
        messages = self._build_messages(user_message, system_prompt, conversation_history)
        return messages, tool_defs, provider

    async def chat(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
        image_data_url: str | None = None,
        source: str = "webui",
    ) -> tuple[str, list[dict[str, Any]], str]:
        messages, tool_defs, provider = await self._prepare_turn(
            member_id, user_message, conversation_history, image_data_url, source
        )

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
        # Run extraction before _prepare_turn so we can yield the report card first
        system_prompt = await self._build_system_prompt(member_id, source)
        if conversation_history is None:
            conversation_history = await self._load_recent_history(member_id, source)
        await self._save_message(member_id, "user", user_message, source)

        report_data: dict | None = None
        if image_data_url is not None:
            report_data = await self._create_report_record(member_id, image_data_url)
            extracted_text = report_data.get("extraction_json", "")
            logger.info("Image extraction done, length=%d, starting text chat stream", len(extracted_text))
            system_prompt += (
                f"\n\n[用户上传了一份报告，AI已自动提取以下结构化信息，"
                f"请基于此信息回答用户问题：]\n{extracted_text}"
            )

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
                reply_text = "".join(full_reply)
                await self._save_message(member_id, "assistant", reply_text, source)
                # Lightweight intent detection (async, non-blocking for the reply)
                intent_data = await self._detect_visit_intent(provider, user_message)
                if intent_data:
                    yield ("intent", json.dumps(intent_data, ensure_ascii=False))
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
        reply_text = "".join(full_reply)
        await self._save_message(member_id, "assistant", reply_text, source)
        # Lightweight intent detection (async, non-blocking for the reply)
        intent_data = await self._detect_visit_intent(provider, user_message)
        if intent_data:
            yield ("intent", json.dumps(intent_data, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_system_prompt(self, member_id: int, source: str = "webui") -> str:
        """Build the system prompt, injecting long-term memory if present (P1-4)."""
        from app.services.member_memory import get_memory_summary

        prompt = SYSTEM_PROMPT
        try:
            from app.services.checkup_recommend import build_health_profile
            profile = await build_health_profile(self.db, member_id)
            light_profile = {
                "基本信息": profile.get("基本信息", {}),
                "生理指标": profile.get("生理指标", {}).get("latest_metrics", {}),
                "既往史与现病史": profile.get("既往史与现病史", {}).get("medical_history", []),
                "家族史": profile.get("家族史", {}),
                "生活方式": profile.get("生活方式", {}),
                "用药记录": profile.get("用药记录", []),
                "过敏信息": profile.get("过敏信息", []),
                "手术史": profile.get("手术史", []),
                "疫苗接种史": profile.get("疫苗接种史", []),
                "特殊状态": profile.get("特殊状态", {}),
            }
            prompt += (
                "\n\n【用户健康画像 — 回答时以此为事实依据，不要编造】\n"
                + json.dumps(light_profile, ensure_ascii=False, default=str)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to build health profile for member %s", member_id)
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
        """Create a ReportRecord, run multimodal extraction, persist, and return dict.

        Orchestrates: parse → save record → build prompt → extract → persist.
        """
        mime, file_content = self._parse_data_url(image_data_url)
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
        await self.db.commit()  # P0-2: commit before long extraction

        self._save_upload_file(record.id, ext, file_content)
        prompt = await self._build_extract_prompt(member_id)

        data, error = await self._run_multimodal_extraction(record, prompt, file_content, mime)
        if error:
            record.status = "rejected"
            await self.db.flush()
            await self.db.commit()
            return {
                "id": record.id,
                "status": "rejected",
                "error": str(error),
                "extraction_json": f"[报告解析失败: {error}] 请用户描述报告内容。",
            }

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
        return self._record_to_dict(record, data)

    @staticmethod
    def _parse_data_url(image_data_url: str) -> tuple[str, bytes]:
        """Parse a data URL into (mime, raw_bytes)."""
        header, b64_data = image_data_url.split(",", 1)
        mime = header.split(":")[1].split(";")[0]
        return mime, base64.b64decode(b64_data)

    @staticmethod
    def _save_upload_file(record_id: int, ext: str, file_content: bytes) -> None:
        """Save uploaded file to disk for thumbnail/preview."""
        from pathlib import Path
        from app.core.config import settings
        # Stage in USERDATA_DIR root (will be relocated on confirm)
        upload_dir = Path(settings.USERDATA_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / f"{record_id}{ext}").write_bytes(file_content)

    async def _build_extract_prompt(self, member_id: int) -> str:
        """Build extraction prompt with member list and existing tag hints."""
        members_result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
        )
        members = members_result.scalars().all()
        member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)

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

        return EXTRACT_PROMPT + f"\n\n当前家庭成员列表：{member_names}\n当前选中的成员ID：{member_id}{tabs_hint}"

    async def _run_multimodal_extraction(
        self, record: ReportRecord, prompt: str, file_content: bytes, mime: str,
    ) -> tuple[dict | None, Exception | None]:
        """Run Map-Reduce multimodal extraction. Returns (data, error)."""
        from app.services.image_utils import (
            MAX_IMAGES_PER_ROUND,
            chunk_data_urls,
            merge_extractions,
            parse_model_json,
            prepare_for_multimodal_async,
            reduce_extraction,
        )
        import asyncio

        multimodal = self.router.get_multimodal_provider()
        data_urls = await prepare_for_multimodal_async(file_content, mime)

        async def extract_batch(batch: list[str], page_hint: str) -> dict:
            user_content: list[dict] = [
                {"type": "text", "text": f"请解析这份健康报告{page_hint}并提取结构化数据, 只提取本批图片中出现的数据, 用相同JSON格式"},
            ]
            for url in batch:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
            messages = [
                Message(role="system", content=prompt),
                Message(role="user", content=user_content),
            ]
            last_err = None
            for attempt in range(3):
                try:
                    logger.info("[report %s] API call attempt %d, sending %d images...", record.id, attempt + 1, len(batch))
                    response = await multimodal.chat(messages, temperature=0.1, max_tokens=4096)
                    logger.info("[report %s] API call attempt %d returned %d chars", record.id, attempt + 1, len(response.content))
                    return parse_model_json(response.content)
                except Exception as e:
                    last_err = e
                    logger.warning("Image extraction attempt %d failed: %s", attempt + 1, e)
                    if attempt < 2:
                        await asyncio.sleep(2)
            raise last_err if last_err else RuntimeError("extraction failed")

        batches = chunk_data_urls(data_urls)
        logger.info("[report %s] Starting extraction: %d batches, %d pages total", record.id, len(batches), len(data_urls))
        batch_results: list[dict] = []
        last_err = None
        for idx, batch in enumerate(batches):
            page_hint = f"(第{idx * MAX_IMAGES_PER_ROUND + 1}-{idx * MAX_IMAGES_PER_ROUND + len(batch)}页)" if len(batches) > 1 else ""
            try:
                logger.info("[report %s] Batch %d/%d starting (%d images)...", record.id, idx + 1, len(batches), len(batch))
                batch_results.append(await extract_batch(batch, page_hint))
                logger.info("[report %s] Batch %d/%d done", record.id, idx + 1, len(batches))
            except Exception as e:
                last_err = e
                logger.error("Batch %d/%d extraction failed for report %s: %s", idx + 1, len(batches), record.id, e)

        if not batch_results:
            return None, last_err or RuntimeError("all batches failed")

        data = normalize_extraction(merge_extractions(batch_results))
        if len(batch_results) > 1:
            try:
                text_provider = self.router.get_text_provider()
                data = await reduce_extraction(data, text_provider)
            except Exception as e:
                logger.warning("Reduce step skipped (%s), using merged data as-is", e)
        return data, None

    @staticmethod
    def _record_to_dict(record: ReportRecord, data: dict) -> dict:
        """Convert a ReportRecord + extraction data into a response dict."""
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
        most recent 10 messages (capped) so the model can continue the previous
        conversation across sessions, not just the last 30 minutes.
        """
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.member_id == member_id, ChatMessage.source == "webui")
            .order_by(ChatMessage.id.desc())
            .limit(10)
        )
        rows = list(result.scalars().all())
        rows.reverse()  # back to ascending order for the context window
        return [Message(role=r.role, content=r.content) for r in rows]

    async def _save_message(self, member_id: int, role: str, content: str, source: str = "webui") -> None:
        """Persist a chat message for future history.

        显式 commit: SSE /chat/stream 里 get_db 依赖尾部 commit 不可靠
        (客户端断开/取消时会被跳过或回滚), 导致 assistant 回复不入库,
        切页再回来历史里就看不到本次对话. 这里统一落库保证 history 完整.
        """
        self.db.add(ChatMessage(member_id=member_id, role=role, content=content, source=source))
        await self.db.flush()
        await self.db.commit()

    def _build_messages(
        self,
        user_message: str,
        system_prompt: str,
        history: list[Message] | None,
    ) -> list[Message]:
        """Build the model message array (方案A):

        - system 提示词在前
        - 历史对话合并为一条 user 消息, 内容前缀标题【用户历史对话】(区分 user/assistant 角色)
        - 本次输入单独一条 user 消息, 内容前缀标题【用户本次输入问题】
        """
        messages: list[Message] = [Message(role="system", content=system_prompt)]
        if history:
            history_text = "\n".join(f"[{r.role}] {r.content}" for r in history)
            messages.append(Message(role="user", content=f"【用户历史对话】\n{history_text}"))
        messages.append(Message(role="user", content=f"【用户本次输入问题】\n{user_message}"))
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

    @staticmethod
    async def _detect_visit_intent(
        provider: ModelProvider,
        user_message: str,
    ) -> dict[str, Any] | None:
        """Lightweight post-reply intent detection.

        Uses a tiny model call (max_tokens=50, temp=0) to check if the user
        expressed intent to visit a doctor. Returns None if no intent detected.
        """
        intent_prompt = (
            "判断以下用户消息是否表达了就医意图（如提到去医院/看医生/挂号/就诊/"
            "找医生/检查一下/复查/看诊等）。只输出JSON，不要其他内容：\n"
            '{"visit_intent": true或false, "complaint": "就医原因摘要，不超过30字"}'
        )
        try:
            response = await provider.chat(
                [
                    Message(role="system", content=intent_prompt),
                    Message(role="user", content=user_message),
                ],
                temperature=0,
                max_tokens=50,
            )
            text = response.content.strip()
            # Strip markdown code block if present
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
            data = json.loads(text)
            if data.get("visit_intent"):
                return {
                    "visit_intent": True,
                    "complaint": data.get("complaint", user_message[:50]),
                }
        except Exception:  # noqa: BLE001
            logger.debug("Visit intent detection failed (non-critical)")
        return None
