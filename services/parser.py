"""PDF parser: converts a PDF file into a Schedule domain object.

Pipeline:
  PDF file path → camelot tables → rows → LessonData items → DaySchedule list → Schedule

The parser has NO knowledge of the database or Telegram.
"""
from __future__ import annotations
import logging
import re
from datetime import date, datetime
from typing import Optional

import camelot

from models.domain import DaySchedule, LessonData, Schedule
from services.normalizer import normalize_lesson, parse_time
from utils.date_utils import get_semester, get_academic_year

logger = logging.getLogger(__name__)

# Date patterns inside day-header cells
# "Понедельник 01.09.26" or "01.09.2026" or "01.09.26"
_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})")
_DAY_NAMES_RU = (
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"
)


def _parse_cell_date(cell_text: str) -> Optional[date]:
    """Extract date from a cell like 'Понедельник 01.09.26'."""
    m = _DATE_RE.search(cell_text)
    if not m:
        return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def _is_day_cell(text: str) -> bool:
    """Return True if the cell appears to be a day-name header."""
    t = text.strip().lower()
    return any(t.startswith(d) for d in _DAY_NAMES_RU) or bool(_DATE_RE.search(t))


def parse_pdf(
    file_path: str,
    group_external_id: str,
    period_start: date,
    period_end: date,
) -> Optional[Schedule]:
    """Parse a schedule PDF and return a Schedule domain object.

    Returns None if the PDF cannot be parsed or yields no usable data.
    """
    try:
        tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
    except Exception as exc:
        logger.error("camelot failed on %s: %s", file_path, exc)
        return None

    if not tables or len(tables) == 0:
        logger.warning("No tables found in %s", file_path)
        return None

    days: list[DaySchedule] = []
    current_day: Optional[DaySchedule] = None
    last_time_start = None
    last_time_end = None

    for table in tables:
        df = table.df
        for _, row in df.iterrows():
            cells = [str(c).replace("\n", " ").strip() for c in row]
            if len(cells) < 3:
                continue

            day_cell = cells[0]
            time_cell = cells[1]
            # Everything from column 2 onwards may be a lesson
            lesson_cells = [c for c in cells[2:] if c]

            # --- detect day header ---
            if day_cell and _is_day_cell(day_cell):
                d = _parse_cell_date(day_cell)
                if d is not None and (period_start <= d <= period_end):
                    if current_day is not None:
                        days.append(current_day)
                    current_day = DaySchedule(date=d)
                    last_time_start = None
                    last_time_end = None

            # --- detect time slot ---
            if time_cell:
                ts, te = parse_time(time_cell)
                if ts is not None:
                    last_time_start = ts
                    last_time_end = te

            # --- parse lesson cells ---
            if current_day is None:
                continue

            for raw in lesson_cells:
                if not raw or raw == "nan":
                    continue
                lesson = normalize_lesson(
                    raw,
                    default_group=group_external_id,
                    start_time=last_time_start,
                    end_time=last_time_end,
                )
                if lesson.title or lesson.raw:
                    current_day.lessons.append(lesson)

    if current_day is not None:
        days.append(current_day)

    # Filter out days with no lessons and days outside period
    days = [d for d in days if d.lessons and period_start <= d.date <= period_end]

    if not days:
        logger.warning("Parser produced 0 usable days for %s", file_path)
        return None

    return Schedule(
        group_external_id=group_external_id,
        period_start=period_start,
        period_end=period_end,
        semester=get_semester(period_start),
        academic_year=get_academic_year(period_start),
        days=days,
    )


def validate_schedule(schedule: Schedule) -> tuple[bool, str]:
    """Basic sanity checks on a parsed schedule.

    Returns (ok, reason). *reason* is non-empty only when ok=False.
    """
    if not schedule.days:
        return False, "Нет дней"
    if schedule.total_lessons < 2:
        return False, f"Слишком мало занятий: {schedule.total_lessons}"
    # Check dates are plausible
    for day in schedule.days:
        if not (schedule.period_start <= day.date <= schedule.period_end):
            return False, f"Дата {day.date} вне периода"
    return True, ""
