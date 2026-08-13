"""Compress images and split PDFs into per-page images for multimodal API."""
from __future__ import annotations

import base64
import io
import json
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
MAX_IMAGES_PER_ROUND = 1

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
    """Deduplicate list of dicts by a key field (or full content if key_field is None)."""
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

    # Dedupe by key_field, keep first occurrence (reduce step will handle merging)
    seen_keys = set()
    out = []
    for it in items:
        if not isinstance(it, dict) or key_field not in it:
            out.append(it)
            continue
        k = str(it[key_field])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        out.append(it)
    return out


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
        "lab_tests": "test_name",
        "exam_findings": "finding_desc",
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


# Reduce 阶段提示词：让文本模型对多批次提取结果做智能整合
_REDUCE_PROMPT = """\
你是一个医疗报告数据整合助手。一份多页体检报告被分成多个批次分别提取，现在需要你将所有批次的结果整合为一份完整、无重复的报告数据。

整合规则：
1. **合并重复项**：同一个指标/诊断/检查可能在多个批次中出现（例如总结页和详情页都提到了甲状腺囊肿），必须合并为一条，保留信息最完整、数值最精确的那个版本
2. **不要丢弃数据**：如果两条记录描述的是同一指标但补充信息不同（如一条有数值一条有建议），合并时应保留所有非空字段
3. **消除矛盾**：如果两条记录数值矛盾，保留更精确/更具体的那个（如 4*3mm 优于 无数值）
4. **统一摘要**：将各批次的 summary 合并为一段连贯、完整的报告摘要，不要遗漏任何异常发现
5. **输出格式**：返回与输入相同的 JSON 结构，不要包含 markdown 代码块标记

请直接输出整合后的 JSON。"""


async def reduce_extraction(
    merged_data: dict,
    text_provider,
) -> dict:
    """Use a text LLM to intelligently consolidate multi-batch extraction results.

    This is the 'reduce' step in a map-reduce pipeline:
    - Map: each batch of PDF pages → structured JSON (done by extract_batch)
    - Merge: concat + simple dedupe (done by merge_extractions)
    - Reduce: text LLM consolidates duplicates, resolves conflicts, unifies summary

    Args:
        merged_data: The merged JSON from merge_extractions()
        text_provider: A text model provider with .chat() method

    Returns:
        Consolidated dict with duplicates merged and conflicts resolved.
    """
    from app.providers.base import Message

    raw_input = json.dumps(merged_data, ensure_ascii=False, indent=2)
    messages = [
        Message(role="system", content=_REDUCE_PROMPT),
        Message(role="user", content=f"以下是多批次提取后合并的原始数据（可能有重复和矛盾）：\n\n{raw_input}"),
    ]
    try:
        response = await text_provider.chat(messages, temperature=0.1, max_tokens=4096)
        raw = response.content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)
        result = json.loads(raw)
        if isinstance(result, dict):
            logger.info("Reduce step: successfully consolidated %d metrics → %d, %d lab_tests → %d, %d exam_findings → %d",
                        len(merged_data.get("metrics", [])), len(result.get("metrics", [])),
                        len(merged_data.get("lab_tests", [])), len(result.get("lab_tests", [])),
                        len(merged_data.get("exam_findings", [])), len(result.get("exam_findings", [])))
            return result
        logger.warning("Reduce step: model returned non-dict, falling back to merged data")
        return merged_data
    except Exception as e:
        logger.warning("Reduce step failed (%s), falling back to merged data", e)
        return merged_data
