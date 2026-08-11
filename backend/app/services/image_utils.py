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
