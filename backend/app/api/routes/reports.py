"""Report management: upload → extract → confirm with state machine."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.utils import compute_age
from app.models.family import FamilyMember
from app.models.health import MetricRecord, Diagnosis, Medication, ReportRecord
from app.prompts import EXTRACT_PROMPT
from app.providers.base import Message
from app.providers.router import ModelRouter, get_model_router
from app.services.extraction_rules import ALLOWED_METRIC_NAMES, filter_metrics, normalize_extraction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/members", tags=["reports"])

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


EXT_MAP = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}

# ReportRecord.file_name is String(256); keep a margin for the stored relative path.
_MAX_FILENAME_LEN = 200


def _safe_filename(raw: str | None) -> str:
    """Normalize a client-supplied upload filename to a bare basename.

    Security (path traversal): the raw ``UploadFile.filename`` is fully
    attacker-controlled. Taking ``Path(...).name`` discards every directory
    component, so values such as ``../../.env`` or ``..\\..\\x`` can never be
    used as a path. Empty / relative-only names fall back to "unknown".
    """
    # Treat Windows separators as separators too, then take the last segment.
    name = Path((raw or "").replace("\\", "/")).name
    # Drop NUL and other control characters that some filesystems reject.
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if not name or name in {".", ".."}:
        return "unknown"
    if len(name) > _MAX_FILENAME_LEN:
        suffix = Path(name).suffix[:16]
        name = Path(name).stem[: _MAX_FILENAME_LEN - len(suffix)] + suffix
    return name


def _structured_root() -> Path:
    """USERDATA_DIR resolved once, used as the containment boundary."""
    return Path(settings.USERDATA_DIR).resolve()


def _oversize_error() -> HTTPException:
    return HTTPException(status_code=413, detail="文件过大，请上传 20MB 以内的文件")


def _read_upload_capped(file: UploadFile) -> bytes:
    """Read an upload without ever buffering more than MAX_FILE_SIZE in memory.

    Starlette spools the body to a temp file, but ``.read()`` with no argument
    still pulls the whole payload into RAM — so a multi-GB upload could exhaust
    memory before the size check ran. Reading in chunks lets us abort as soon
    as the limit is crossed.
    """
    declared = getattr(file, "size", None)
    if declared is not None and declared > MAX_FILE_SIZE:
        raise _oversize_error()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise _oversize_error()
        chunks.append(chunk)
    return b"".join(chunks)


def _resolve_file_path(record: ReportRecord) -> Path:
    """Find a report's file on disk — try structured path (file_name) then legacy (id.ext).

    Security: the structured path derived from ``file_name`` is resolved and
    checked to stay inside USERDATA_DIR. Previously a crafted ``file_name``
    (e.g. ``../.env``) was joined directly onto USERDATA_DIR, which allowed
    arbitrary file reads through the download endpoint and arbitrary file
    moves during relocation.
    """
    if record.file_name and "/" in record.file_name:
        root = _structured_root()
        candidate = (root / record.file_name).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return candidate
    ext = EXT_MAP.get(record.file_type, ".bin")
    legacy = (UPLOAD_DIR / f"{record.id}{ext}").resolve()
    if legacy.is_file():
        return legacy
    raise FileNotFoundError(f"Report file not found for record {record.id}")


async def _relocate_to_structured(db, record: ReportRecord, member: FamilyMember) -> None:
    """Move a report file from legacy path to structured member/year/month path."""
    from app.services.file_storage import build_file_path
    ext = EXT_MAP.get(record.file_type, ".bin")
    old_path = _resolve_file_path(record)
    if not old_path.exists():
        return
    report_date = record.report_date
    new_path = build_file_path(
        member_name=member.name,
        report_type=record.report_type,
        report_date=report_date,
        ext=ext,
        member_id=member.id,
    )
    if new_path == old_path:
        return
    if new_path.exists():
        new_path = new_path.with_name(f"{new_path.stem}_{record.id}{new_path.suffix}")
    import shutil
    shutil.move(str(old_path), str(new_path))
    try:
        rel = new_path.relative_to(Path(settings.USERDATA_DIR))
        record.file_name = str(rel)
    except ValueError:
        record.file_name = new_path.name


# ---- Schemas ----

class MetricItem(BaseModel):
    metric_name: str
    label: str
    value: Any
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
    value: Any
    unit: Optional[str] = None
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    is_abnormal: bool = False

class ExamFindingItem(BaseModel):
    finding_category: str
    finding_desc: str
    value_num: Optional[Any] = None
    unit: Optional[str] = None
    conclusion: Optional[str] = None
    is_abnormal: bool = False

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


def _save_and_convert(file: UploadFile, record_id: int) -> tuple[str, str, int]:
    """Save file to disk and return (data_url, mime, size)."""
    content = file.file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请上传 20MB 以内的文件")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"不支持的文件类型: {mime}，仅支持 JPG/PNG/WebP/PDF")
    # Save to disk
    ext = EXT_MAP.get(mime, ".bin")
    file_path = UPLOAD_DIR / f"{record_id}{ext}"
    file_path.write_bytes(content)
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime};base64,{b64}", mime, len(content)


def _report_to_response(r: ReportRecord) -> ReportRecordResponse:
    extraction = None
    if r.extraction:
        try:
            extraction = ExtractionResult(**json.loads(r.extraction))
        except Exception:
            logger.warning("Failed to parse extraction JSON for report %s", r.id)
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

    # Cheap validations first: type before reading any bytes into memory.
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"不支持的文件类型: {mime}，仅支持 JPG/PNG/WebP/PDF")
    content = _read_upload_capped(file)
    size = len(content)

    # Create report record first to get id
    record = ReportRecord(
        member_id=member_id,
        file_name=_safe_filename(file.filename),
        file_type=mime,
        file_size=size,
        source=source,
        status="extracting",
    )
    db.add(record)
    await db.flush()
    # P0-2: commit immediately so the extracting record is visible in DB.
    await db.commit()

    # Save file to disk using record.id
    ext = EXT_MAP.get(mime, ".bin")
    file_path = UPLOAD_DIR / f"{record.id}{ext}"
    file_path.write_bytes(content)

    # Build data_url for AI extraction
    from app.services.image_utils import (
        MAX_IMAGES_PER_ROUND,
        chunk_data_urls,
        merge_extractions,
        parse_model_json,
        prepare_for_multimodal_async,
    )
    # P0-1: use async version to avoid blocking the event loop.
    data_urls = await prepare_for_multimodal_async(content, mime)

    # Run extraction
    provider = model_router.get_multimodal_provider()
    members_result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
    )
    members = members_result.scalars().all()
    member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)
    # Fetch existing lab report_name tabs and exam category tabs for this member
    existing_result = await db.execute(
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

    import asyncio

    batches = chunk_data_urls(data_urls)
    batch_results: list[dict] = []
    last_err = None
    for idx, batch in enumerate(batches):
        page_hint = f"(第{idx * MAX_IMAGES_PER_ROUND + 1}-{idx * MAX_IMAGES_PER_ROUND + len(batch)}页)" if len(batches) > 1 else ""
        try:
            batch_results.append(
                await _extract_batch(provider, prompt, batch, page_hint, record.id)
            )
        except Exception as e:
            last_err = e
            logger.error(
                "Batch %d/%d extraction failed for report %s: %s",
                idx + 1, len(batches), record.id, e,
            )

    if not batch_results:
        logger.error("Extraction failed (all batches) for report %s", record.id)
        record.status = "rejected"
        await db.flush()
        await db.commit()
        raise HTTPException(status_code=500, detail="AI 解析失败，请重试")

    data = normalize_extraction(merge_extractions(batch_results))
    ext = ExtractionResult(**data)

    record.extraction = json.dumps(data, ensure_ascii=False)
    record.report_type = ext.report_type
    record.report_date = _parse_optional_date(ext.report_date)
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


def _pick_items(items: list, indices: Optional[List[int]]) -> list:
    """Select items by user-chosen indices, ignoring malformed indices.

    Negative indices previously slipped through ``i < len(items)`` and silently
    selected from the end of the list (or raised IndexError -> 500).
    """
    if indices is None:
        return items
    return [items[i] for i in indices if isinstance(i, int) and 0 <= i < len(items)]


def _parse_optional_date(raw: Optional[str]):
    """Parse an AI-supplied date, returning None instead of raising.

    Report dates come from the model and may be formatted in ways
    ``datetime.fromisoformat`` rejects (e.g. "2024/05/01" or "2024年7月26日").
    A malformed value must not fail the whole archival.
    """
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _build_report_metric(
    member_id: int,
    metric_name: str,
    value: Any,
    unit: Optional[str],
    explicit_lower: Optional[float],
    explicit_upper: Optional[float],
    ai_is_abnormal: bool,
    age: Optional[int],
    measured_at: datetime,
    context: Optional[str],
) -> MetricRecord:
    """Build a MetricRecord using server-side reference-range rules.

    This is the key fix for the report-archival path: previously the row was
    written with whatever ``reference_lower`` / ``reference_upper`` /
    ``is_abnormal`` the model returned, and ``is_critical`` was never set at all.
    A report containing a systolic pressure of 205 therefore landed as "normal"
    and never produced a critical alert or a follow-up task.
    """
    from app.core.reference_ranges import evaluate_metric, plausible_range_error

    is_numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_numeric:
        numeric_value = float(value)
        lower, upper, abnormal, critical = evaluate_metric(
            metric_name, numeric_value, age, explicit_lower, explicit_upper
        )
        # An implausible OCR/model value (e.g. systolic 99999) must not raise a
        # false "危急值，请尽快就医" alert. Keep it visible as abnormal, but never
        # critical, and log it for troubleshooting.
        if critical and plausible_range_error(metric_name, numeric_value):
            logger.warning(
                "Implausible report metric %s=%s; suppressing critical flag",
                metric_name, numeric_value,
            )
            critical = False
        text_value = None
    else:
        # Non-numeric result (e.g. "淡黄色"): keep the model's bounds/flag and
        # never derive a critical flag from the 0 placeholder.
        numeric_value = 0.0
        lower, upper = explicit_lower, explicit_upper
        abnormal, critical = bool(ai_is_abnormal), False
        text_value = str(value) if value is not None else None

    return MetricRecord(
        member_id=member_id,
        metric_name=metric_name,
        value=numeric_value,
        text_value=text_value,
        unit=unit,
        reference_lower=lower,
        reference_upper=upper,
        is_abnormal=abnormal,
        is_critical=critical,
        measured_at=measured_at,
        source_type="report",
        context=context,
    )


async def _extract_batch(
    provider,
    prompt: str,
    batch: list[str],
    page_hint: str,
    report_id: int,
) -> dict:
    """Extract structured JSON from one batch of image data URLs.

    Retries up to 3 times with a short backoff. Shared by the upload and retry
    paths so both honour the multimodal model's per-request image limit.
    """
    import asyncio

    from app.services.image_utils import parse_model_json

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
            response = await provider.chat(messages, temperature=0.1, max_tokens=4096)
            # P0-3: unified JSON parsing
            return parse_model_json(response.content)
        except Exception as e:
            last_err = e
            logger.warning(
                "Extraction attempt %d failed for report %s: %s", attempt + 1, report_id, e
            )
            if attempt < 2:
                await asyncio.sleep(2)
    raise last_err if last_err else RuntimeError("extraction failed")


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

    # State machine guard: only a report whose extraction finished and awaits
    # human review may be archived. This also makes confirm idempotent — a
    # repeated call now returns 409 instead of duplicating every metric,
    # diagnosis and medication (which silently doubled health records).
    if record.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"当前状态 {record.status} 不可入档，仅待确认（pending）的报告可入档",
        )

    report_dt = _parse_optional_date(ext.report_date) or now

    # Filter by user selection
    metrics = _pick_items(ext.metrics, payload.keep_metric_indices)
    metrics = [m for m in metrics if m.metric_name in ALLOWED_METRIC_NAMES]
    diagnoses = _pick_items(ext.diagnoses, payload.keep_diagnosis_indices)
    medications = _pick_items(ext.medications, payload.keep_medication_indices)
    lab_tests = _pick_items(ext.lab_tests, payload.keep_lab_test_indices)
    exam_findings = _pick_items(ext.exam_findings, payload.keep_exam_finding_indices)

    member = await db.get(FamilyMember, member_id)
    age = compute_age(member.birth_date) if member else None

    saved_metrics = 0
    for m in metrics:
        row = _build_report_metric(
            member_id=member_id,
            metric_name=m.metric_name,
            value=m.value,
            unit=m.unit,
            explicit_lower=m.reference_lower,
            explicit_upper=m.reference_upper,
            ai_is_abnormal=m.is_abnormal,
            age=age,
            measured_at=report_dt,
            context=record.file_name or ext.report_type,
        )
        db.add(row)
        await db.flush()  # need the id for auto-generated follow-up tasks
        saved_metrics += 1
        # Auto-task hook (same behaviour as manual metric entry): only critical
        # values raise an immediate "seek care / re-test" to-do.
        if row.is_critical:
            try:
                from app.services import task_service

                await task_service.handle_metric_recorded(
                    db, member_id, row.metric_name, row.is_abnormal, row.is_critical, row.id
                )
            except Exception:  # noqa: BLE001
                logger.exception("task generation failed for report metric %s", row.id)

    saved_diagnoses = 0
    for d in diagnoses:
        obj = Diagnosis(
            member_id=member_id,
            disease_name=d.disease_name,
            severity=d.severity,
            diagnosed_date=(
                dt.date() if (dt := _parse_optional_date(d.diagnosed_date)) else None
            ),
            status="active",
        )
        db.add(obj)
        await db.flush()
        saved_diagnoses += 1
        try:
            from app.services import task_service

            await task_service.handle_diagnosis_added(
                db, member_id, obj.disease_name, obj.id, obj.status
            )
        except Exception:  # noqa: BLE001
            logger.exception("task generation failed for report diagnosis %s", obj.id)

    saved_medications = 0
    report_date_value = _parse_optional_date(ext.report_date)
    for med in medications:
        obj = Medication(
            member_id=member_id,
            drug_name=med.drug_name,
            dosage=med.dosage,
            frequency=med.frequency,
            start_date=report_date_value.date() if report_date_value else None,
        )
        db.add(obj)
        await db.flush()
        saved_medications += 1
        try:
            from app.services import task_service

            await task_service.handle_medication_added(
                db, member_id, obj.drug_name, obj.id, obj.end_date
            )
        except Exception:  # noqa: BLE001
            logger.exception("task generation failed for report medication %s", obj.id)

    saved_lab_tests = 0
    for lt in lab_tests:
        db.add(_build_report_metric(
            member_id=member_id,
            metric_name=f"lab:{lt.report_name}:{lt.test_name}",
            value=lt.value,
            unit=lt.unit,
            explicit_lower=lt.reference_lower,
            explicit_upper=lt.reference_upper,
            ai_is_abnormal=lt.is_abnormal,
            age=age,
            measured_at=report_dt,
            context=lt.report_name,
        ))
        saved_lab_tests += 1

    saved_exam_findings = 0
    for ef in exam_findings:
        value_str = f"{ef.value_num}" if ef.value_num is not None else ""
        is_num_ef = isinstance(ef.value_num, (int, float)) and not isinstance(ef.value_num, bool)
        db.add(MetricRecord(
            member_id=member_id,
            metric_name=f"exam:{ef.finding_category}:{ef.finding_desc}",
            value=float(ef.value_num) if is_num_ef else 0,
            # Preserve a non-numeric finding instead of dropping it: previously
            # text was only stored when value_num was non-numeric AND not None,
            # so a purely descriptive finding lost its content entirely.
            text_value=(
                None if is_num_ef
                else (str(ef.value_num) if ef.value_num is not None else (ef.conclusion or None))
            ),
            unit=ef.unit,
            is_abnormal=ef.is_abnormal,
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

    # Update report metadata from extraction for file naming
    record.report_type = ext.report_type or record.report_type
    record.report_date = report_dt if ext.report_date else record.report_date

    # Move file to structured path: member_name/year/month/report_name_date.ext
    try:
        member = await db.get(FamilyMember, member_id)
        if member:
            await _relocate_to_structured(db, record, member)
            # Sync summary .md files into the member's folder
            from app.services.file_storage import sync_summary_files
            await sync_summary_files(db, member_id)
    except Exception as e:
        logger.warning("Failed to relocate file for report %s: %s", record.id, e)

    await db.flush()

    # Generate embedding for RAG. Wrapped in a SAVEPOINT: a failure inside
    # (e.g. a chunk flush rejected by the DB) used to poison the outer
    # transaction, so the following commit raised PendingRollbackError and threw
    # away every record this request had just archived — while the report file
    # had already been moved aside, leaving it unreachable.
    try:
        from app.services.rag import generate_and_store_embedding

        async with db.begin_nested():
            await generate_and_store_embedding(
                db, member_id, record, payload.extraction.model_dump()
            )
    except Exception as e:
        logger.warning("Embedding generation failed for report %s: %s", record.id, e)

    await db.commit()
    return ConfirmResponse(
        saved_metrics=saved_metrics,
        saved_diagnoses=saved_diagnoses,
        saved_medications=saved_medications,
        saved_lab_tests=saved_lab_tests,
        saved_exam_findings=saved_exam_findings,
    )



@router.get("/{member_id}/reports/{report_id}/file")
async def get_report_file(
    member_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Serve the original uploaded file for thumbnail/preview."""
    result = await db.execute(
        select(ReportRecord).where(
            ReportRecord.id == report_id,
            ReportRecord.member_id == member_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    # Find file on disk (structured path or legacy)
    try:
        file_path = _resolve_file_path(r)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件未找到")
    from fastapi.responses import FileResponse
    return FileResponse(path=str(file_path), media_type=r.file_type)


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


@router.post("/{member_id}/reports/{report_id}/retry", response_model=ReportRecordResponse)
async def retry_extraction(
    member_id: int,
    report_id: int,
    model_router: ModelRouter = Depends(get_model_router),
    db: AsyncSession = Depends(get_db),
) -> ReportRecordResponse:
    """Re-run AI extraction for a rejected/failed report."""
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
    # "extracting" is included so a record orphaned by a crashed/failed request
    # can be recovered instead of being stuck in "解析中" forever.
    if record.status not in ("rejected", "cancelled", "uploaded", "extracting"):
        raise HTTPException(status_code=400, detail=f"当前状态 {record.status} 不可重试")

    try:
        file_path = _resolve_file_path(record)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="原始文件未找到")
    content = file_path.read_bytes()
    b64 = base64.b64encode(content).decode("utf-8")
    data_url = f"data:{record.file_type};base64,{b64}"

    record.status = "extracting"
    record.extraction = None
    await db.flush()
    await db.commit()  # P0-2: commit before long extraction

    from app.services.image_utils import prepare_for_multimodal_async
    data_urls = await prepare_for_multimodal_async(content, record.file_type)

    provider = model_router.get_multimodal_provider()
    members_result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
    )
    members = members_result.scalars().all()
    member_names = ", ".join(f"{m.name}(关系:{m.member_relation})" for m in members)
    existing_result = await db.execute(
        select(MetricRecord.metric_name).where(
            MetricRecord.member_id == member_id,
            MetricRecord.metric_name.like('lab:%') | MetricRecord.metric_name.like('exam:%'),
        ).distinct()
    )
    existing_names = [r2[0] for r2 in existing_result.all()]
    existing_lab_reports = sorted({n.split(':', 2)[1] for n in existing_names if n.startswith('lab:') and len(n.split(':')) >= 3})
    existing_exam_cats = sorted({n.split(':', 2)[1] for n in existing_names if n.startswith('exam:') and len(n.split(':')) >= 3})
    tabs_hint = f"\n已有检验报告标签：{existing_lab_reports}" if existing_lab_reports else "\n已有检验报告标签：无"
    tabs_hint += f"\n已有检查分类标签：{existing_exam_cats}" if existing_exam_cats else "\n已有检查分类标签：无"
    tabs_hint += "\n重要：report_name 和 finding_category 必须优先复用已有标签，仅当无法匹配时才新建简短标准名。"
    prompt = EXTRACT_PROMPT + f"\n\n当前家庭成员列表：{member_names}\n当前选中的成员ID：{member_id}{tabs_hint}"
    user_content2: list[dict] = [{"type": "text", "text": "请解析这份健康报告并提取结构化数据"}]
    for url in data_urls:
        user_content2.append({"type": "image_url", "image_url": {"url": url}})
    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=user_content2),
    ]

    import asyncio

    # Use the same page chunking as upload. Sending every page in one request
    # exceeded the multimodal model's per-request image limit, so retrying a
    # multi-page PDF always failed with a provider error.
    from app.services.image_utils import MAX_IMAGES_PER_ROUND, chunk_data_urls, merge_extractions

    batches = chunk_data_urls(data_urls)
    batch_results: list[dict] = []
    last_err = None
    for idx, batch in enumerate(batches):
        page_hint = (
            f"(第{idx * MAX_IMAGES_PER_ROUND + 1}-{idx * MAX_IMAGES_PER_ROUND + len(batch)}页)"
            if len(batches) > 1 else ""
        )
        for attempt in range(3):
            try:
                batch_results.append(await _extract_batch(provider, prompt, batch, page_hint, record.id))
                break
            except Exception as e:
                last_err = e
                logger.warning(
                    "Retry extraction batch %d/%d attempt %d failed for report %s: %s",
                    idx + 1, len(batches), attempt + 1, record.id, e,
                )
                if attempt < 2:
                    await asyncio.sleep(2)

    if not batch_results:
        logger.error("Retry extraction failed after 3 attempts for report %s", record.id)
        record.status = "rejected"
        await db.flush()
        await db.commit()
        return _report_to_response(record)

    data = normalize_extraction(merge_extractions(batch_results))
    try:
        ext = ExtractionResult(**data)
    except Exception as e:  # noqa: BLE001
        logger.error("Retry extraction produced invalid shape for report %s: %s", record.id, e)
        record.status = "rejected"
        await db.flush()
        await db.commit()
        return _report_to_response(record)

    record.extraction = json.dumps(data, ensure_ascii=False)
    record.report_type = ext.report_type
    record.report_date = _parse_optional_date(ext.report_date)
    record.summary = ext.summary
    record.patient_name = ext.patient_name
    record.status = "pending"
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return _report_to_response(record)


@router.post("/{member_id}/reports/{report_id}/cancel", response_model=ReportRecordResponse)
async def cancel_report(
    member_id: int,
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> ReportRecordResponse:
    """Cancel a pending report."""
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
    if record.status not in ("pending", "extracting", "uploaded"):
        raise HTTPException(status_code=400, detail=f"当前状态 {record.status} 不可取消")
    record.status = "cancelled"
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return _report_to_response(record)


@router.post("/{member_id}/reports/rebuild-embeddings")
async def rebuild_embeddings(
    member_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Rebuild embeddings for all archived reports of a member."""
    await _ensure_member(db, member_id)
    r = await db.execute(
        select(ReportRecord).where(
            ReportRecord.member_id == member_id,
            ReportRecord.status == "archived",
        )
    )
    records = r.scalars().all()

    from app.services.rag import generate_and_store_embedding
    success = 0
    skipped = 0
    failed = 0
    for record in records:
        if not record.confirmed_extraction:
            skipped += 1
            continue
        try:
            extraction_data = json.loads(record.confirmed_extraction)
            chunk = await generate_and_store_embedding(db, member_id, record, extraction_data)
            if chunk:
                success += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("Rebuild embedding failed for report %s: %s", record.id, e)
            failed += 1

    await db.commit()
    return {
        "total": len(records),
        "success": success,
        "skipped": skipped,
        "failed": failed,
    }
