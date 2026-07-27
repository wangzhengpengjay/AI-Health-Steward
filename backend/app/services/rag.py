"""RAG service — generates and stores report embeddings for semantic retrieval.

Called after report confirmation (archived). Builds a text representation
from the confirmed extraction, generates embedding, and persists to report_chunks.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import ReportChunk, ReportRecord
from app.providers.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


def _build_chunk_text(member_id: int, report: ReportRecord, extraction: dict) -> str:
    """Build a text representation of a report for embedding."""
    parts: list[str] = []

    if report.report_type:
        parts.append(f"报告类型: {report.report_type}")
    if report.report_date:
        parts.append(f"报告日期: {report.report_date.strftime('%Y-%m-%d')}")
    if report.patient_name:
        parts.append(f"患者: {report.patient_name}")
    if report.summary:
        parts.append(f"摘要: {report.summary}")

    # Metrics
    metrics = extraction.get("metrics", [])
    if metrics:
        lines = ["指标:"]
        for m in metrics:
            abnormal = " (异常)" if m.get("is_abnormal") else ""
            ref = ""
            if m.get("reference_lower") is not None and m.get("reference_upper") is not None:
                ref = f" 参考范围:{m['reference_lower']}-{m['reference_upper']}"
            lines.append(f"  {m.get('label', m.get('metric_name', ''))}: {m.get('value')}{m.get('unit', '')}{ref}{abnormal}")
        parts.append("\n".join(lines))

    # Lab tests
    lab_tests = extraction.get("lab_tests", [])
    if lab_tests:
        lines = ["检验:"]
        for lt in lab_tests:
            abnormal = " (异常)" if lt.get("is_abnormal") else ""
            ref = ""
            if lt.get("reference_lower") is not None and lt.get("reference_upper") is not None:
                ref = f" 参考范围:{lt['reference_lower']}-{lt['reference_upper']}"
            lines.append(f"  {lt.get('report_name', '')}/{lt.get('test_name', '')}: {lt.get('value')}{lt.get('unit', '')}{ref}{abnormal}")
        parts.append("\n".join(lines))

    # Exam findings
    exams = extraction.get("exam_findings", [])
    if exams:
        lines = ["检查异常:"]
        for ef in exams:
            val = f" {ef.get('value_num', '')}{ef.get('unit', '')}" if ef.get("value_num") is not None else ""
            conclusion = f" 结论:{ef.get('conclusion', '')}" if ef.get("conclusion") else ""
            lines.append(f"  {ef.get('finding_category', '')}: {ef.get('finding_desc', '')}{val}{conclusion}")
        parts.append("\n".join(lines))

    # Diagnoses
    diagnoses = extraction.get("diagnoses", [])
    if diagnoses:
        lines = ["诊断:"]
        for d in diagnoses:
            sev = f" ({d['severity']})" if d.get("severity") else ""
            lines.append(f"  {d.get('disease_name', '')}{sev}")
        parts.append("\n".join(lines))

    # Medications
    meds = extraction.get("medications", [])
    if meds:
        lines = ["用药:"]
        for m in meds:
            lines.append(f"  {m.get('drug_name', '')} {m.get('dosage', '')} {m.get('frequency', '')}")
        parts.append("\n".join(lines))

    return "\n".join(parts)


async def generate_and_store_embedding(
    db: AsyncSession,
    member_id: int,
    report: ReportRecord,
    extraction_data: dict,
) -> Optional[ReportChunk]:
    """Generate embedding for a report and store in report_chunks.

    Returns the ReportChunk if successful, None if embedding not configured or failed.
    """
    provider = EmbeddingProvider()
    if not provider.is_configured:
        logger.info("Embedding model not configured, skipping embedding for report %s", report.id)
        return None

    chunk_text = _build_chunk_text(member_id, report, extraction_data)
    if not chunk_text.strip():
        logger.warning("Empty chunk text for report %s, skipping", report.id)
        return None

    try:
        embedding = await provider.embed(chunk_text)
    except Exception as e:
        logger.error("Embedding generation failed for report %s: %s", report.id, e)
        return None

    # Delete existing chunk for this report (in case of re-archival)
    await db.execute(
        delete(ReportChunk).where(ReportChunk.report_id == report.id)
    )

    chunk = ReportChunk(
        member_id=member_id,
        report_id=report.id,
        chunk_text=chunk_text,
        embedding=embedding,
    )
    db.add(chunk)
    await db.flush()
    logger.info("Embedding stored for report %s (chunk_id=%s)", report.id, chunk.id)
    return chunk


async def search_reports(
    db: AsyncSession,
    member_id: int,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Semantic search across a member's archived reports.

    Returns list of {chunk_text, report_id, distance} sorted by relevance.
    """
    provider = EmbeddingProvider()
    if not provider.is_configured:
        return []

    try:
        query_embedding = await provider.embed(query)
    except Exception as e:
        logger.error("Query embedding failed: %s", e)
        return []

    from sqlalchemy import text as sql_text

    stmt = sql_text("""
        SELECT rc.id, rc.chunk_text, rc.report_id,
               rc.embedding <=> :query_vec AS distance
        FROM report_chunks rc
        WHERE rc.member_id = :member_id
        ORDER BY rc.embedding <=> :query_vec
        LIMIT :limit
    """)

    result = await db.execute(stmt, {
        "query_vec": str(query_embedding),
        "member_id": member_id,
        "limit": limit,
    })

    return [
        {
            "chunk_text": row.chunk_text,
            "report_id": row.report_id,
            "distance": float(row.distance),
        }
        for row in result
    ]
