"""File storage helper — builds structured local paths for user health data.

Layout:  USERDATA_DIR / member_name / year / month / report_name_date.ext
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings


_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe_name(text: str, fallback: str = "未命名") -> str:
    """Sanitise a string for use as a file/dir name."""
    cleaned = _SAFE_RE.sub("_", text).strip().strip(".")
    return cleaned if cleaned else fallback


def get_userdata_dir() -> Path:
    """Return the configured user-data root, creating it if needed."""
    p = Path(settings.USERDATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def build_file_path(
    member_name: str,
    report_type: Optional[str],
    report_date: Optional[datetime],
    ext: str,
    member_id: int,
) -> Path:
    """Build a structured file path under USERDATA_DIR.

    Structure: member_name / year / month / report_name_date.ext
    """
    root = get_userdata_dir()
    member_dir = _safe_name(member_name, fallback=f"member_{member_id}")

    if report_date:
        year = str(report_date.year)
        month = f"{report_date.month:02d}"
    else:
        year = "未知日期"
        month = ""

    if report_type:
        name_prefix = _safe_name(report_type, fallback="报告")
    else:
        name_prefix = "报告"

    date_str = report_date.strftime("%Y%m%d") if report_date else datetime.now().strftime("%Y%m%d")
    filename = f"{name_prefix}_{date_str}{ext}"

    dir_path = root / member_dir / year
    if month:
        dir_path = dir_path / month
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / filename


def build_legacy_path(record_id: int, ext: str) -> Path:
    """Old-style flat path for backward compatibility reads."""
    return get_userdata_dir() / f"{record_id}{ext}"


def build_summary_path(
    member_name: str,
    period: str,
    period_start,
    period_end,
    member_id: int,
) -> Path:
    """Build path for a monthly or annual summary .md file.

    Monthly: member_name / year / month / 月度总结_YYYY-MM.md
    Annual:  member_name / year / 年度总结_YYYY.md
    """
    root = get_userdata_dir()
    member_dir = _safe_name(member_name, fallback=f"member_{member_id}")

    if period == "annual":
        year = str(period_start.year)
        filename = f"年度总结_{period_start.year}.md"
        dir_path = root / member_dir / year
    else:
        year = str(period_start.year)
        month = f"{period_start.month:02d}"
        filename = f"月度总结_{period_start.year}-{month}.md"
        dir_path = root / member_dir / year / month

    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / filename


async def sync_summary_files(db, member_id: int) -> int:
    """Sync all monthly & annual summaries for a member to .md files.

    Returns count of files written.
    """
    from sqlalchemy import select
    from app.models.family import FamilyMember
    from app.models.summaries import HealthSummary

    member = await db.get(FamilyMember, member_id)
    if not member:
        return 0

    result = await db.execute(
        select(HealthSummary).where(
            HealthSummary.member_id == member_id,
            HealthSummary.period.in_(["monthly", "annual"]),
        ).order_by(HealthSummary.period_start.asc())
    )
    summaries = result.scalars().all()

    count = 0
    for s in summaries:
        path = build_summary_path(
            member.name, s.period, s.period_start, s.period_end, member.id
        )
        path.write_text(s.content, encoding="utf-8")
        count += 1
    return count
