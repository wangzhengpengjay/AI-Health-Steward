"""Report management: upload → extract → confirm with state machine."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import MetricRecord, Diagnosis, Medication, ReportRecord
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
3. 检查指标（exam_findings）只提取异常发现，不提取正常检查结果
4. 如果报告中有姓名，尝试识别归属人

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

class ReportRecordResponse(BaseModel):
    id: int
    member_id: int
    file_name: str
    file_type: str
    file_size: int
    source: str
    status: str
    extraction: Optional[ExtractionResult] = None
    report_type: Optional[str] = None
    report_date: Optional[str] = None
    summary: Optional[str] = None
    patient_name: Optional[str] = None
    saved_metrics: int = 0
    saved_diagnoses: int = 0
    saved_medications: int = 0
    saved_lab_tests: int = 0
    saved_exam_findings: int = 0
    created_at: str
    updated_at: str


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    r = await db.execute(
        select(FamilyMember.id).where(FamilyMember.id == member_id, FamilyMember.is_deleted.is_(False))
    )
    if r.scalars().first() is None:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")


def _file_to_data_url(file: UploadFile) -> tuple[str, str, int]:
    content = file.file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请上传 20MB 以内的文件")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"不支持的文件类型: {mime}，仅支持 JPG/PNG/WebP/PDF")
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime};base64,{b64}", mime, len(content)


def _report_to_response(r: ReportRecord) -> ReportRecordResponse:
    extraction = None
    if r.extraction:
        try:
            extraction = ExtractionResult(**json.loads(r.extraction))
        except Exception:
            extraction = None
    return ReportRecordResponse(
        id=r.id,
        member_id=r.member_id,
        file_name=r.file_name,
        file_type=r.file_type,
        file_size=r.file_size,
        source=r.source,
        status=r.status,
        extraction=extraction,
        report_type=r.report_type,
        report_date=r.report_date.isoformat() if r.report_date else None,
        summary=r.summary,
        patient_name=r.patient_name,
        saved_metrics=r.saved_metrics,
        saved_diagnoses=r.saved_diagnoses,
        saved_medications=r.saved_medications,
        saved_lab_tests=r.saved_lab_tests,
        saved_exam_findings=r.saved_exam_findings,
        created_at=r.created_at.isoformat() if r.created_at else "",
        updated_at=r.updated_at.isoformat() if r.updated_at else "",
    )


# ---- Endpoints ----

@router.get("/{member_id}/reports", response_model=list[ReportRecordResponse])
async def list_reports(
    member_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[ReportRecordResponse]:
    """List all report records for a member, newest first."""
    await _ensure_member(db, member_id)
    r = await db.execute(
        select(ReportRecord)
        .where(ReportRecord.member_id == member_id)
        .order_by(ReportRecord.created_at.desc())
    )
    return [_report_to_response(row) for row in r.scalars().all()]


@router.post("/{member_id}/reports/upload", response_model=ReportRecordResponse)
async def upload_report(
    member_id: int,
    source: str = "report_page",
    file: UploadFile = File(...),
    model_router: ModelRouter = Depends(get_model_router),
    db: AsyncSession = Depends(get_db),
) -> ReportRecordResponse:
    """Upload a report file, create record, run AI extraction, return result."""
    await _ensure_member(db, member_id)
    data_url, mime, size = _file_to_data_url(file)

    # Create report record
    record = ReportRecord(
        member_id=member_id,
        file_name=file.filename or "unknown",
        file_type=mime,
        file_size=size,
        source=source,
        status="extracting",
    )
    db.add(record)
    await db.flush()

    # Run extraction
    provider = model_router.get_multimodal_provider()
    members_result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
    )
    members = members_result.scalars().all()
    member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)
    prompt = EXTRACT_PROMPT + f"\n\n当前家庭成员列表：{member_names}\n当前选中的成员ID：{member_id}"

    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=[
            {"type": "text", "text": "请解析这份健康报告并提取结构化数据"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]),
    ]

    import asyncio
    last_err = None
    for attempt in range(3):
        try:
            response = await provider.chat(messages, temperature=0.1, max_tokens=4096)
            raw = response.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                raw = "\n".join(lines)
            data = json.loads(raw)
            ext = ExtractionResult(**data)
            break
        except Exception as e:
            last_err = e
            logger.warning("Extraction attempt %d failed for report %s: %s", attempt + 1, record.id, e)
            if attempt < 2:
                await asyncio.sleep(2)
    else:
        logger.error("Extraction failed after 3 attempts for report %s", record.id)
        record.status = "rejected"
        await db.flush()
        await db.commit()
        raise HTTPException(status_code=500, detail="AI 解析失败，请重试")

    record.extraction = json.dumps(data, ensure_ascii=False)
    record.report_type = ext.report_type
    record.report_date = datetime.fromisoformat(ext.report_date) if ext.report_date else None
    record.summary = ext.summary
    record.patient_name = ext.patient_name
    record.status = "pending"
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return _report_to_response(record)


@router.get("/{member_id}/reports/{report_id}", response_model=ReportRecordResponse)
async def get_report(
    member_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> ReportRecordResponse:
    """Get a single report record with extraction details."""
    await _ensure_member(db, member_id)
    r = await db.execute(
        select(ReportRecord).where(
            ReportRecord.id == report_id,
            ReportRecord.member_id == member_id,
        )
    )
    record = r.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _report_to_response(record)


@router.post("/{member_id}/reports/{report_id}/confirm", response_model=ConfirmResponse)
async def confirm_report(
    member_id: int,
    report_id: int,
    payload: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ConfirmResponse:
    """Save confirmed extraction results to health records, update report status."""
    await _ensure_member(db, member_id)
    r = await db.execute(
        select(ReportRecord).where(
            ReportRecord.id == report_id,
            ReportRecord.member_id == member_id,
        )
    )
    record = r.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")

    ext = payload.extraction
    now = datetime.now(timezone.utc)
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
    lab_tests = ext.lab_tests
    if payload.keep_lab_test_indices is not None:
        lab_tests = [ext.lab_tests[i] for i in payload.keep_lab_test_indices if i < len(ext.lab_tests)]
    exam_findings = ext.exam_findings
    if payload.keep_exam_finding_indices is not None:
        exam_findings = [ext.exam_findings[i] for i in payload.keep_exam_finding_indices if i < len(ext.exam_findings)]

    saved_metrics = 0
    for m in metrics:
        db.add(MetricRecord(
            member_id=member_id,
            metric_name=m.metric_name,
            value=m.value,
            unit=m.unit,
            reference_lower=m.reference_lower,
            reference_upper=m.reference_upper,
            is_abnormal=m.is_abnormal,
            measured_at=report_dt,
            source_type="report",
            context=record.file_name or ext.report_type,
        ))
        saved_metrics += 1

    saved_diagnoses = 0
    for d in diagnoses:
        db.add(Diagnosis(
            member_id=member_id,
            disease_name=d.disease_name,
            severity=d.severity,
            diagnosed_date=datetime.fromisoformat(d.diagnosed_date).date() if d.diagnosed_date else None,
            status="active",
        ))
        saved_diagnoses += 1

    saved_medications = 0
    for med in medications:
        db.add(Medication(
            member_id=member_id,
            drug_name=med.drug_name,
            dosage=med.dosage,
            frequency=med.frequency,
            start_date=datetime.fromisoformat(ext.report_date).date() if ext.report_date else None,
        ))
        saved_medications += 1

    saved_lab_tests = 0
    for lt in lab_tests:
        db.add(MetricRecord(
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
        ))
        saved_lab_tests += 1

    saved_exam_findings = 0
    for ef in exam_findings:
        value_str = f"{ef.value_num}" if ef.value_num is not None else ""
        db.add(MetricRecord(
            member_id=member_id,
            metric_name=f"exam:{ef.finding_category}:{ef.finding_desc}",
            value=ef.value_num if ef.value_num is not None else 0,
            unit=ef.unit,
            is_abnormal=True,
            measured_at=report_dt,
            source_type="report",
            context=f"{ef.finding_category}: {value_str} ({ef.conclusion or ''})",
        ))
        saved_exam_findings += 1

    # Update report record
    record.confirmed_extraction = json.dumps(payload.extraction.model_dump(), ensure_ascii=False)
    record.status = "archived"
    record.saved_metrics = saved_metrics
    record.saved_diagnoses = saved_diagnoses
    record.saved_medications = saved_medications
    record.saved_lab_tests = saved_lab_tests
    record.saved_exam_findings = saved_exam_findings

    await db.flush()
    await db.commit()
    return ConfirmResponse(
        saved_metrics=saved_metrics,
        saved_diagnoses=saved_diagnoses,
        saved_medications=saved_medications,
        saved_lab_tests=saved_lab_tests,
        saved_exam_findings=saved_exam_findings,
    )


@router.delete("/{member_id}/reports/{report_id}")
async def delete_report(
    member_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a report record (and its stored extraction). Does NOT delete archived health data."""
    await _ensure_member(db, member_id)
    r = await db.execute(
        select(ReportRecord).where(
            ReportRecord.id == report_id,
            ReportRecord.member_id == member_id,
        )
    )
    record = r.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    await db.delete(record)
    await db.commit()
    return {"ok": True}
