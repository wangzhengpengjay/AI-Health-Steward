"""Report ingestion: structured extraction with user confirmation."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import MetricRecord, Diagnosis, Medication
from app.providers.base import Message
from app.providers.router import ModelRouter, get_model_router

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/members", tags=["reports"])

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

EXTRACT_PROMPT = """\
你是一个医疗报告解析助手。请仔细分析上传的健康报告图片/PDF，提取以下结构化信息。

要求：
1. 只提取报告中明确出现的数据，不要编造或推断
2. 如果某个字段无法识别，返回null或空数组
3. 如果报告中有姓名，尝试识别归属人

请严格按照以下JSON格式返回（不要包含markdown代码块标记）：
{
  "patient_name": "报告中识别到的姓名，没有则为null",
  "report_type": "报告类型，如 体检报告/血液检查/血压记录 等",
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
      "report_name": "检验报告名称，如 血常规/肝功能/肾功能",
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
      "finding_category": "检查发现的标准分类，如 肺结节/甲状腺结节/肝囊肿/乳腺结节 等。用于归类聚合，必须是简短的标准类别名",
      "finding_desc": "该检查发现的具体诊断描述，如 右肺水平裂旁微小磨玻璃结节/左叶甲状腺低回声结节 等",
      "value_num": 可量化的数值或null，如结节大小3则填3，
      "unit": "数值的单位或null，如 mm",
      "conclusion": "检查结论或建议，如 建议随诊/考虑良性 等"
    }
  ],
  "summary": "报告摘要，1-3句话概述"
}
"""


# ---- Schemas ----

class MetricItem(BaseModel):
    metric_name: str
    label: str
    value: float
    unit: Optional[str] = None
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    is_abnormal: bool = False

class DiagnosisItem(BaseModel):
    disease_name: str
    severity: Optional[str] = None
    diagnosed_date: Optional[str] = None

class MedicationItem(BaseModel):
    drug_name: str
    dosage: str
    frequency: str

class LabTestItem(BaseModel):
    report_name: str
    test_name: str
    value: float
    unit: Optional[str] = None
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    is_abnormal: bool = False

class ExamFindingItem(BaseModel):
    finding_category: str
    finding_desc: str
    value_num: Optional[float] = None
    unit: Optional[str] = None
    conclusion: Optional[str] = None

class ExtractionResult(BaseModel):
    patient_name: Optional[str] = None
    report_type: Optional[str] = None
    report_date: Optional[str] = None
    metrics: List[MetricItem] = []
    diagnoses: List[DiagnosisItem] = []
    medications: List[MedicationItem] = []
    lab_tests: List[LabTestItem] = []
    exam_findings: List[ExamFindingItem] = []
    summary: Optional[str] = None

class ConfirmRequest(BaseModel):
    extraction: ExtractionResult
    file_name: Optional[str] = None
    # Items the user confirmed (indices to keep); empty = keep all
    keep_metric_indices: Optional[List[int]] = None
    keep_diagnosis_indices: Optional[List[int]] = None
    keep_medication_indices: Optional[List[int]] = None
    keep_lab_test_indices: Optional[List[int]] = None
    keep_exam_finding_indices: Optional[List[int]] = None

class ConfirmResponse(BaseModel):
    saved_metrics: int
    saved_diagnoses: int
    saved_medications: int
    saved_lab_tests: int
    saved_exam_findings: int


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    r = await db.execute(
        select(FamilyMember.id).where(FamilyMember.id == member_id, FamilyMember.is_deleted.is_(False))
    )
    if r.scalars().first() is None:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")


def _file_to_data_url(file: UploadFile) -> str:
    content = file.file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请上传 20MB 以内的文件")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"不支持的文件类型: {mime}，仅支持 JPG/PNG/WebP/PDF")
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime};base64,{b64}"


@router.post("/{member_id}/reports/extract", response_model=ExtractionResult)
async def extract_report(
    member_id: int,
    file: UploadFile = File(...),
    model_router: ModelRouter = Depends(get_model_router),
    db: AsyncSession = Depends(get_db),
) -> ExtractionResult:
    """Upload a report file and get structured extraction via multimodal AI."""
    await _ensure_member(db, member_id)
    provider = model_router.get_multimodal_provider()
    data_url = _file_to_data_url(file)

    # Get member names for name matching
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
    )
    members = result.scalars().all()
    member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)

    prompt = EXTRACT_PROMPT + f"\n\n当前家庭成员列表：{member_names}\n当前选中的成员ID：{member_id}"

    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=[
            {"type": "text", "text": "请解析这份健康报告并提取结构化数据"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]),
    ]

    response = await provider.chat(messages, temperature=0.1, max_tokens=4096)
    raw = response.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last line (```json ... ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse extraction JSON: %s\nRaw: %s", e, raw[:500])
        raise HTTPException(status_code=500, detail="AI 返回格式异常，请重试")

    return ExtractionResult(**data)


@router.post("/{member_id}/reports/confirm", response_model=ConfirmResponse)
async def confirm_report(
    member_id: int,
    payload: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ConfirmResponse:
    """Save confirmed extraction results to the database with source tracing."""
    await _ensure_member(db, member_id)
    ext = payload.extraction
    now = datetime.now(timezone.utc)
    # Parse report_date string to datetime
    report_dt = now
    if ext.report_date:
        try:
            report_dt = datetime.fromisoformat(ext.report_date)
        except (ValueError, TypeError):
            report_dt = now

    # Filter by user selection
    metrics = ext.metrics
    if payload.keep_metric_indices is not None:
        metrics = [metrics[i] for i in payload.keep_metric_indices if i < len(metrics)]
    diagnoses = ext.diagnoses
    if payload.keep_diagnosis_indices is not None:
        diagnoses = [diagnoses[i] for i in payload.keep_diagnosis_indices if i < len(diagnoses)]
    medications = ext.medications
    if payload.keep_medication_indices is not None:
        medications = [medications[i] for i in payload.keep_medication_indices if i < len(medications)]

    saved_metrics = 0
    for m in metrics:
        record = MetricRecord(
            member_id=member_id,
            metric_name=m.metric_name,
            value=m.value,
            unit=m.unit,
            reference_lower=m.reference_lower,
            reference_upper=m.reference_upper,
            is_abnormal=m.is_abnormal,
            measured_at=report_dt,
            source_type="report",
            context=payload.file_name or ext.report_type,
        )
        db.add(record)
        saved_metrics += 1

    saved_diagnoses = 0
    for d in diagnoses:
        record = Diagnosis(
            member_id=member_id,
            disease_name=d.disease_name,
            severity=d.severity,
            diagnosed_date=datetime.fromisoformat(d.diagnosed_date).date() if d.diagnosed_date else None,
            status="active",
        )
        db.add(record)
        saved_diagnoses += 1

    saved_medications = 0
    for med in medications:
        record = Medication(
            member_id=member_id,
            drug_name=med.drug_name,
            dosage=med.dosage,
            frequency=med.frequency,
            start_date=datetime.fromisoformat(ext.report_date).date() if ext.report_date else None,
        )
        db.add(record)
        saved_medications += 1

    # Lab tests: store as metric records with metric_name="lab:{report_name}:{test_name}"
    saved_lab_tests = 0
    for lt in (ext.lab_tests if payload.keep_lab_test_indices is None
               else [ext.lab_tests[i] for i in payload.keep_lab_test_indices if i < len(ext.lab_tests)]):
        record = MetricRecord(
            member_id=member_id,
            metric_name=f"lab:{lt.report_name}:{lt.test_name}",
            value=lt.value,
            unit=lt.unit,
            reference_lower=lt.reference_lower,
            reference_upper=lt.reference_upper,
            is_abnormal=lt.is_abnormal,
            measured_at=report_dt,
            source_type="report",
            context=lt.report_name,
        )
        db.add(record)
        saved_lab_tests += 1

    # Exam findings: store as metric records with metric_name="exam:{category}:{item}"
    saved_exam_findings = 0
    for ef in (ext.exam_findings if payload.keep_exam_finding_indices is None
               else [ext.exam_findings[i] for i in payload.keep_exam_finding_indices if i < len(ext.exam_findings)]):
        record = MetricRecord(
            member_id=member_id,
            metric_name=f"exam:{ef.finding_category}:{ef.finding_desc}",
            value=ef.value_num if ef.value_num is not None else 0,
            unit=ef.unit,
            is_abnormal=True,  # exam findings are always notable
            measured_at=report_dt,
            source_type="report",
            context=f"{ef.finding_category}: {ef.value_str} ({ef.conclusion or ''})",
        )
        db.add(record)
        saved_exam_findings += 1

    await db.flush()
    return ConfirmResponse(
        saved_metrics=saved_metrics,
        saved_diagnoses=saved_diagnoses,
        saved_medications=saved_medications,
        saved_lab_tests=saved_lab_tests,
        saved_exam_findings=saved_exam_findings,
    )
