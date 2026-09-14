"""Regression tests for report file-path safety (path traversal).

Covers the fix for: client-controlled ``UploadFile.filename`` being stored raw
and later joined directly onto USERDATA_DIR, which allowed arbitrary file reads
through ``GET /members/{id}/reports/{id}/file`` and arbitrary file moves during
relocation.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.api.routes.reports import (
    MAX_FILE_SIZE,
    _read_upload_capped,
    _resolve_file_path,
    _safe_filename,
)


# --------------------------------------------------------------------------
# _safe_filename — strips every directory component
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("report.png", "report.png"),
        ("../README.md", "README.md"),
        ("../../.env", ".env"),
        ("../../../../etc/passwd", "passwd"),
        ("..\\..\\windows.png", "windows.png"),
        ("/absolute/path/scan.pdf", "scan.pdf"),
        ("nested/dir/report.jpg", "report.jpg"),
        ("..", "unknown"),
        (".", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
        ("   ", "unknown"),
    ],
)
def test_safe_filename_strips_directories(raw, expected):
    assert _safe_filename(raw) == expected


def test_safe_filename_never_contains_separator():
    for evil in ("../a/b/c.png", "..\\..\\x.png", "/etc/shadow", "a/../../b"):
        result = _safe_filename(evil)
        assert "/" not in result
        assert "\\" not in result
        assert ".." != result


def test_safe_filename_is_length_capped():
    # ReportRecord.file_name is String(256); keep the stored name well inside it.
    long_name = "a" * 5000 + ".png"
    result = _safe_filename(long_name)
    assert len(result) <= 200
    assert result.endswith(".png")


# --------------------------------------------------------------------------
# _resolve_file_path — containment boundary
# --------------------------------------------------------------------------

class _FakeRecord:
    def __init__(self, file_name: str, file_type: str = "image/png", id: int = 1):
        self.file_name = file_name
        self.file_type = file_type
        self.id = id


def test_resolve_rejects_escape_outside_userdata(monkeypatch):
    """A stored '../../.env' style name must never resolve outside USERDATA_DIR."""
    with tempfile.TemporaryDirectory() as tmp:
        userdata = Path(tmp) / "userdata"
        userdata.mkdir()
        secret = Path(tmp) / ".env"
        secret.write_text("MULTIMODAL_API_KEY=leaked", encoding="utf-8")

        monkeypatch.setattr(
            "app.api.routes.reports.settings.USERDATA_DIR", str(userdata), raising=False
        )
        # file_name must contain "/" to enter the structured branch
        record = _FakeRecord(file_name="../.env")
        with pytest.raises(FileNotFoundError):
            _resolve_file_path(record)


def test_resolve_allows_legitimate_structured_subpath(monkeypatch):
    """Normal member/year/month relative paths inside USERDATA_DIR still work."""
    with tempfile.TemporaryDirectory() as tmp:
        userdata = Path(tmp) / "userdata"
        target = userdata / "王" / "2025" / "01" / "体检报告_2025-01-01.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"png")

        monkeypatch.setattr(
            "app.api.routes.reports.settings.USERDATA_DIR", str(userdata), raising=False
        )
        record = _FakeRecord(file_name="王/2025/01/体检报告_2025-01-01.png")
        assert _resolve_file_path(record) == target.resolve()


def test_resolve_rejects_directory(monkeypatch):
    """Containment check must also reject directories, not just escaped paths."""
    with tempfile.TemporaryDirectory() as tmp:
        userdata = Path(tmp) / "userdata"
        (userdata / "sub").mkdir(parents=True)
        monkeypatch.setattr(
            "app.api.routes.reports.settings.USERDATA_DIR", str(userdata), raising=False
        )
        record = _FakeRecord(file_name="sub")
        # "sub" has no "/" so it goes to the legacy branch; still must not serve a dir
        with pytest.raises(FileNotFoundError):
            _resolve_file_path(record)


# --------------------------------------------------------------------------
# _read_upload_capped — bounded memory read
# --------------------------------------------------------------------------

class _FakeUpload:
    def __init__(self, data: bytes, size: int | None = None):
        import io

        self.file = io.BytesIO(data)
        self.size = len(data) if size is None else size


def test_read_upload_capped_returns_full_content():
    payload = b"x" * 1024
    assert _read_upload_capped(_FakeUpload(payload)) == payload


def test_read_upload_capped_rejects_declared_oversize():
    from fastapi import HTTPException

    upload = _FakeUpload(b"small", size=MAX_FILE_SIZE + 1)
    with pytest.raises(HTTPException) as exc:
        _read_upload_capped(upload)
    assert exc.value.status_code == 413


def test_read_upload_capped_rejects_actual_oversize():
    """Even if the declared size lies, the chunked reader must abort."""
    from fastapi import HTTPException

    upload = _FakeUpload(b"y" * (MAX_FILE_SIZE + 10), size=1)
    with pytest.raises(HTTPException) as exc:
        _read_upload_capped(upload)
    assert exc.value.status_code == 413
