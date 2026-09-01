"""Schedule service: retrieve schedule data for users.

All methods return DaySchedule lists (domain objects) suitable for formatting.
They run synchronously; call via asyncio.to_thread() from async contexts.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Optional

from database.connection import get_session
from database.models import Lesson, Subject, TimeSlot
from models.domain import DaySchedule, LessonData
from repositories import schedule_repository as sr
from repositories import group_repository as gr

logger = logging.getLogger(__name__)


def _lesson_to_domain(lesson: Lesson) -> LessonData:
    subj: Optional[Subject] = lesson.subject
    slot: Optional[TimeSlot] = lesson.time_slot
    return LessonData(
        raw=lesson.raw_text or "",
        title=subj.title if subj else None,
        lesson_type=subj.lesson_type if subj else None,
        teacher=subj.teacher.full_name if (subj and subj.teacher) else None,
        room=lesson.room.name if lesson.room else None,
        subgroup=subj.subgroup if subj else None,
        start_time=slot.start_time if slot else None,
        end_time=slot.end_time if slot else None,
    )


def _group_into_days(lessons: list[Lesson]) -> list[DaySchedule]:
    """Convert a flat lesson list to DaySchedule objects, grouped by date."""
    day_map: dict[date, DaySchedule] = {}
    for l in lessons:
        d = l.day.date
        if d not in day_map:
            day_map[d] = DaySchedule(date=d)
        day_map[d].lessons.append(_lesson_to_domain(l))
    return [day_map[d] for d in sorted(day_map)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_today(group_id: int, target_date: Optional[date] = None) -> list[DaySchedule]:
    """Return lessons for today (or *target_date*)."""
    if target_date is None:
        target_date = date.today()
    with get_session() as session:
        lessons = sr.get_lessons_for_date(session, group_id, target_date)
    return _group_into_days(lessons)


def get_tomorrow(group_id: int) -> list[DaySchedule]:
    return get_today(group_id, target_date=date.today() + timedelta(days=1))


def get_week(group_id: int, start: Optional[date] = None) -> list[DaySchedule]:
    """Return lessons for the current Mon–Sun week."""
    if start is None:
        today = date.today()
        start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=6)  # Sunday
    with get_session() as session:
        lessons = sr.get_lessons_for_date_range(session, group_id, start, end)
    return _group_into_days(lessons)


def get_two_weeks(group_id: int) -> list[DaySchedule]:
    """Return lessons for the next 14 calendar days from today."""
    start = date.today()
    end = start + timedelta(days=13)
    with get_session() as session:
        lessons = sr.get_lessons_for_date_range(session, group_id, start, end)
    return _group_into_days(lessons)


def get_group_by_external_id(external_id: str):
    with get_session() as session:
        return gr.get_by_external_id(session, external_id)


def get_all_active_groups():
    with get_session() as session:
        return gr.get_active(session)
