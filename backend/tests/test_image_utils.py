"""Tests for image/PDF multimodal preprocessing utilities."""
from __future__ import annotations

import base64
import io

import pytest

from app.services.image_utils import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_ROUND,
    _compress_image_bytes,
    _pdf_to_images,
    chunk_data_urls,
    merge_extractions,
    prepare_for_multimodal,
)


def _small_png() -> bytes:
    """Return a tiny valid PNG bytes payload."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (120, 120, 120)).save(buf, format="PNG")
    return buf.getvalue()


def _small_pdf(page_count: int = 2) -> bytes:
    """Return a multi-page PDF payload."""
    import fitz

    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=200, height=150)
        page.insert_text((50, 75), "health")
    pdf = doc.tobytes()
    doc.close()
    return pdf


def test_compress_image_returns_jpeg_under_limit():
    raw = _small_png()
    out = _compress_image_bytes(raw, "image/png")
    # It should convert PNG->JPEG (smaller, but valid image)
    assert len(out) <= MAX_IMAGE_BYTES
    # JPEG magic header FF D8
    assert out[:2] == b"\xff\xd8"


def test_prepare_image_single_data_url():
    raw = _small_png()
    urls = prepare_for_multimodal(raw, "image/png")
    assert len(urls) == 1
    assert urls[0].startswith("data:image/jpeg;base64,")
    payload = base64.b64decode(urls[0].split(",", 1)[1])
    assert payload[:2] == b"\xff\xd8"


def test_prepare_pdf_one_url_per_page():
    raw = _small_pdf(page_count=3)
    urls = prepare_for_multimodal(raw, "application/pdf")
    assert len(urls) == 3
    assert all(u.startswith("data:image/jpeg;base64,") for u in urls)


def test_pdf_to_images_count():
    raw = _small_pdf(page_count=2)
    images = _pdf_to_images(raw)
    assert len(images) == 2
    # Each page compressed to JPEG
    assert all(im[:2] == b"\xff\xd8" for im in images)


def test_prepare_unknown_mime_treated_as_image():
    raw = _small_png()
    urls = prepare_for_multimodal(raw, "image/jpeg")  # passes through
    assert len(urls) == 1


def test_chunk_data_urls_splits_over_limit():
    urls = [f"data:image/jpeg;base64,{i}" for i in range(15)]
    batches = chunk_data_urls(urls)
    assert [len(b) for b in batches] == [1] * 15
    assert sum(len(b) for b in batches) == 15
    assert all(len(b) <= MAX_IMAGES_PER_ROUND for b in batches)


def test_chunk_data_urls_under_limit_single_batch():
    urls = [f"u{i}" for i in range(1)]
    batches = chunk_data_urls(urls)
    assert len(batches) == 1
    assert len(batches[0]) == 1


def test_merge_extractions_dedupes_lists_and_takes_first_scalar():
    b1 = {
        "patient_name": "王正鹏",
        "report_type": "检验报告单",
        "report_date": "2026-07-26",
        "metrics": [{"metric_name": "systolic_blood_pressure", "value": 152}],
        "lab_tests": [{"report_name": "肝功能", "test_name": "谷丙转氨酶", "value": 40}],
        "diagnoses": [],
        "medications": [],
        "exam_findings": [],
        "summary": "第一页摘要",
    }
    b2 = {
        "patient_name": None,
        "report_type": None,
        "report_date": None,
        "metrics": [
            {"metric_name": "systolic_blood_pressure", "value": 152},  # dup -> dedupe
            {"metric_name": "diastolic_blood_pressure", "value": 99},
        ],
        "lab_tests": [{"report_name": "血常规", "test_name": "白细胞", "value": 6.5}],
        "diagnoses": [],
        "medications": [],
        "exam_findings": [],
        "summary": "第二页摘要",
    }
    merged = merge_extractions([b1, b2])
    # scalar: first non-null wins
    assert merged["patient_name"] == "王正鹏"
    assert merged["report_type"] == "检验报告单"
    assert merged["report_date"] == "2026-07-26"
    # lists merged + deduped
    assert len(merged["metrics"]) == 2
    assert len(merged["lab_tests"]) == 2
    # summaries joined
    assert merged["summary"] == "第一页摘要\n第二页摘要"


def test_merge_extractions_single_batch_returns_as_is():
    b = {"metrics": [], "summary": "only"}
    assert merge_extractions([b]) == b


def test_max_images_per_round_constant_defined():
    assert MAX_IMAGES_PER_ROUND == 1
