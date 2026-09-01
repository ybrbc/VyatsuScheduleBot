"""Date utilities for biweekly schedule period calculation.

Academic year 2024-2025 started 2024-09-02 (Monday) — this is the base date.
Periods are 14-day (Mon–Sun) windows repeating every 2 weeks indefinitely.

Known period starts confirmed from the test server:
  2024-09-02, 2024-11-11, 2024-12-09
  2025-09-01, 2025-11-10, 2025-12-08
  2026-09-01 (shifted from computed 2026-08-31 → Sep 1 fix applied)
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional

# First Monday of academic year 2024-2025
_BASE = datetime(2024, 9, 2)


def _make_datetime(d: date | datetime) -> datetime:
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day)


def get_biweekly_periods(
    target: Optional[date | datetime] = None, num: int = 2
) -> list[tuple[date, date]]:
    """Return *num* consecutive biweekly periods starting from the one that
    contains *target* (defaults to today).

    The returned dates are *filename dates* — the Aug-31→Sep-1 correction
    is already applied inside each tuple.
    """
    if target is None:
        target = datetime.now()
    dt = _make_datetime(target)

    days_from_base = (dt - _BASE).days
    period_idx = max(0, days_from_base // 14)

    periods: list[tuple[date, date]] = []
    for i in range(num):
        raw_start = _BASE + timedelta(days=(period_idx + i) * 14)
        raw_end = raw_start + timedelta(days=13)
        start, end = _apply_filename_fix(raw_start, raw_end)
        periods.append((start.date(), end.date()))

    return periods


def _apply_filename_fix(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """When a period *bridges* August → September the university publishes
    the PDF with September 1 as start (not August 31).

    Only applies when start is in August AND end is already in September,
    i.e. the 14-day window crosses the Aug/Sep boundary.
    (Mid-August periods that end in August are entirely pre-semester
     and are filtered out by should_download(), so we leave them alone.)
    """
    if start.month == 8 and end.month == 9:
        start = datetime(start.year, 9, 1)
    return start, end


def should_download(start: date, end: date) -> bool:
    """Returns False for periods entirely in summer break (Jun / Jul / Aug-only)."""
    # Full summer months
    if start.month in (6, 7):
        return False
    # August-only period (both start and end in August)
    if start.month == 8 and end.month == 8:
        return False
    return True


def get_semester(period_start: date) -> int:
    """1 = fall (Aug-Jan), 2 = spring (Feb-Jun)."""
    return 1 if period_start.month in (8, 9, 10, 11, 12, 1) else 2


def get_academic_year(period_start: date) -> str:
    """E.g. '2026-2027' for a September 2026 start."""
    if period_start.month >= 9:
        return f"{period_start.year}-{period_start.year + 1}"
    return f"{period_start.year - 1}-{period_start.year}"


def fmt_period_date(d: date) -> str:
    """Format date as DDMMYYYY for use in PDF filenames."""
    return d.strftime("%d%m%Y")


def build_pdf_filename(group_id: str, semester: int, start: date, end: date) -> str:
    """Construct the exact filename used on the server."""
    return f"{group_id}_{semester}_{fmt_period_date(start)}_{fmt_period_date(end)}.pdf"
