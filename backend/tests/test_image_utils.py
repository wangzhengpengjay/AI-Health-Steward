"""Tests for image/PDF multimodal preprocessing utilities."""
from __future__ import annotations

import base64
import io

import pytest

from app.services.image_utils import (
    MAX_IMAGE_BYTES,
    _compress_image_bytes,
    _pdf_to_images,
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
