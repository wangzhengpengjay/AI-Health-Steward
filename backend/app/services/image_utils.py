"""Compress images and split PDFs into per-page images for multimodal API."""
from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_LONG_EDGE = 2048
JPEG_QUALITY = 80


def _compress_image_bytes(raw: bytes, mime: str) -> bytes:
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed, skipping compression")
        return raw

    img = Image.open(io.BytesIO(raw))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    w, h = img.size
    long_edge = max(w, h)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    result = buf.getvalue()

    q = JPEG_QUALITY
    while len(result) > MAX_IMAGE_BYTES and q > 30:
        q -= 15
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        result = buf.getvalue()

    return result


def _pdf_to_images(raw: bytes) -> list[bytes]:
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF not installed, cannot process PDF")

    images: list[bytes] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    for page in doc:
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        compressed = _compress_image_bytes(png_bytes, "image/png")
        images.append(compressed)
    doc.close()
    return images


def prepare_for_multimodal(raw: bytes, mime: str) -> list[str]:
    """Convert raw file to list of data URLs for multimodal API.

    Images: compress -> single data URL.
    PDFs: each page -> compressed JPEG -> one data URL per page.
    """
    if mime == "application/pdf":
        image_list = _pdf_to_images(raw)
    else:
        image_list = [_compress_image_bytes(raw, mime)]

    data_urls: list[str] = []
    for img_bytes in image_list:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        data_urls.append(f"data:image/jpeg;base64,{b64}")
    return data_urls


# 多模态 API 单轮图片数上限(实测确定 = 4)。
# 多页 PDF 会每页转一张图, 一次发送过多会触发 code 10043 "image count in one round exceeds limit"。
# 实测: 4 张成功, 5 张失败 -> 上限为 4。
MAX_IMAGES_PER_ROUND = 4

# 提取 JSON 中需要合并去重的数组字段(按内容去重, 忽略顺序)
_LIST_FIELDS = ["metrics", "diagnoses", "medications", "lab_tests", "exam_findings"]
# 提取 JSON 中取第一个非 null 的标量字段
_SCALAR_FIELDS = ["patient_name", "report_type", "report_date"]


def chunk_data_urls(urls: list[str], batch_size: int = MAX_IMAGES_PER_ROUND) -> list[list[str]]:
    """Split data URLs into batches each with at most ``batch_size`` images.

    Multi-page PDFs produce one data URL per page. Sending them all in a single
    multimodal round can exceed the provider's per-round image limit (e.g. iFlytek
    code 10043), so we chunk them for sequential per-batch extraction.
    """
    return [urls[i : i + batch_size] for i in range(0, len(urls), batch_size)]


def _dedupe(items: list, key_field: str | None = None) -> list:
    """Deduplicate list of dicts by a key field (or full content if key_field is None).

    When key_field is provided, items with the same key_field value are merged:
    the one with more non-null fields is kept, and text fields are concatenated
    if they differ.
    """
    if not key_field:
        # Fall back to full-content dedupe
        seen = set()
        out = []
        for it in items:
            if isinstance(it, dict):
                key = tuple(sorted((k, str(v)) for k, v in it.items()))
            else:
                key = (str(it),)
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    # Dedupe by key_field, merge richer items
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for it in items:
        if not isinstance(it, dict) or key_field not in it:
            # Non-dict or missing key: keep as-is via content dedupe
            k = json.dumps(it, ensure_ascii=False, sort_keys=True) if isinstance(it, dict) else str(it)
            if k not in by_key:
                by_key[k] = it  # type: ignore
                order.append(k)
            continue
        k = str(it[key_field])
        if k not in by_key:
            by_key[k] = it
            order.append(k)
        else:
            existing = by_key[k]
            # Count non-null fields in each
            existing_rich = sum(1 for v in existing.values() if v is not None and v != "" and v != 0)
            new_rich = sum(1 for v in it.values() if v is not None and v != "" and v != 0)
            if new_rich > existing_rich:
                # Merge: carry over any non-null fields from existing that are null in new
                for fk, fv in existing.items():
                    if fv is not None and fv != "" and (it.get(fk) is None or it.get(fk) == ""):
                        it[fk] = fv
                by_key[k] = it
            else:
                # Merge: carry over any non-null fields from new that are null in existing
                for fk, fv in it.items():
                    if fv is not None and fv != "" and (existing.get(fk) is None or existing.get(fk) == ""):
                        existing[fk] = fv
    return [by_key[k] for k in order]


def merge_extractions(batches: list[dict]) -> dict:
    """Merge several per-batch extraction JSONs into a single report JSON.

    Each batch is a full EXTRACT_PROMPT-shaped dict from a subset of the PDF pages.
    We merge list fields (dedupe by content), take the first non-null value for scalar
    fields (patient_name / report_type / report_date), and join summaries.
    """
    if not batches:
        return {}
    if len(batches) == 1:
        return batches[0]

    merged: dict = {}
    # list fields: concat + dedupe by key field
    _KEY_FIELDS = {
        "metrics": "metric_name",
        "diagnoses": "disease_name",
        "medications": "drug_name",
        "lab_tests": "report_name",
        "exam_findings": "finding_category",
    }
    for field in _LIST_FIELDS:
        items = []
        for b in batches:
            v = b.get(field) or []
            if isinstance(v, list):
                items.extend(v)
        if items:
            merged[field] = _dedupe(items, key_field=_KEY_FIELDS.get(field))
        else:
            merged[field] = []
    # scalar fields: first non-null
    for field in _SCALAR_FIELDS:
        merged[field] = next((b.get(field) for b in batches if b.get(field)), None)
    # summary: join non-empty summaries
    summaries = [b.get("summary") for b in batches if b.get("summary")]
    merged["summary"] = "\n".join(summaries) if summaries else None
    return merged
