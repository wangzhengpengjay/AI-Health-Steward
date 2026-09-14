"""Regression tests for the data export / wipe endpoints.

Covers:
- export & wipe covering every health table (previously surgeries, vaccinations,
  report_chunks and data_provenances were omitted)
- the wipe confirmation guard actually being required
- stored report files being removed by a wipe, with a guard that refuses to
  purge a filesystem root or the user's home directory
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routes import settings as settings_routes
from app.api.routes.settings import _health_tables, _purge_user_files


# --------------------------------------------------------------------------
# Table coverage
# --------------------------------------------------------------------------

def test_health_tables_include_previously_missing_tables():
    names = {t.name for t in _health_tables()}
    for required in ("surgeries", "vaccinations", "report_chunks", "data_provenances"):
        assert required in names, f"{required} missing from export/wipe scope"


def test_health_tables_exclude_config_tables():
    names = {t.name for t in _health_tables()}
    # Secrets/config must not be exported and must survive a wipe.
    assert "feishu_channels" not in names
    assert "alembic_version" not in names


def test_health_tables_cover_all_family_data():
    names = {t.name for t in _health_tables()}
    assert "family_members" in names
    assert "metric_records" in names
    assert "chat_messages" in names
    assert "health_tasks" in names
    assert "scale_results" in names


# --------------------------------------------------------------------------
# Wipe confirmation guard
# --------------------------------------------------------------------------

def _call_wipe(confirm, db=None):
    return asyncio.run(
        settings_routes.wipe_all_data(confirm=confirm, db=db or AsyncMock())
    )


@pytest.mark.parametrize("confirm", ["", "delete", "DELETE ", "yes", "true"])
def test_wipe_requires_exact_confirmation(confirm):
    """A missing/incorrect confirm param must never wipe.

    The parameter previously defaulted to "DELETE", so a bare
    ``DELETE /settings/data`` wiped the whole database.
    """
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _call_wipe(confirm, db)
    assert exc.value.status_code == 400
    # Nothing must have been executed against the database.
    assert not db.execute.called


def test_wipe_accepts_exact_confirmation():
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=0)
    result = asyncio.run(
        settings_routes.wipe_all_data(confirm="DELETE", db=db)
    )
    assert result["deleted"] is True
    assert "tables" in result
    assert db.execute.called


# --------------------------------------------------------------------------
# File purge
# --------------------------------------------------------------------------

def _fake_settings(tmp_root: Path, upload_root: Path):
    return SimpleNamespace(USERDATA_DIR=str(tmp_root), UPLOAD_DIR=str(upload_root))


def test_purge_removes_files_and_directories(tmp_path, monkeypatch):
    userdata = tmp_path / "userdata"
    uploads = tmp_path / "uploads"
    (userdata / "王" / "2025" / "01").mkdir(parents=True)
    (userdata / "王" / "2025" / "01" / "报告.png").write_bytes(b"x")
    uploads.mkdir()
    (uploads / "1.png").write_bytes(b"y")

    monkeypatch.setattr(
        settings_routes, "get_settings", lambda: _fake_settings(userdata, uploads)
    )
    removed = _purge_user_files()

    assert removed == 2
    assert list(userdata.iterdir()) == []
    assert list(uploads.iterdir()) == []


def test_purge_refuses_filesystem_root(tmp_path, monkeypatch):
    """A misconfigured USERDATA_DIR must not become a destructive wipe."""
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: _fake_settings(Path("/"), tmp_path / "uploads"),
    )
    # Must not raise and must not delete anything at "/".
    assert _purge_user_files() == 0


def test_purge_refuses_home_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: _fake_settings(Path.home(), tmp_path / "uploads"),
    )
    assert _purge_user_files() == 0


def test_purge_tolerates_missing_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: _fake_settings(tmp_path / "nope", tmp_path / "also-nope"),
    )
    assert _purge_user_files() == 0
