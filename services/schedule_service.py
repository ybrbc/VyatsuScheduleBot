"""Schedule service: retrieve lessons from DB as domain objects."""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Optional

from database.connection import get_session
from database.models import Lesson
from models.domain import DaySchedule, LessonData
from repositories import schedule_repository as sr
from utils.formatter import SubjectFilters, has_visible_lessons

logger = logging.getLogger(__name__)


def _lesson_to_domain(lesson: Lesson) -> LessonData:
    subj = lesson.subject
    slot = lesson.time_slot
    return LessonData(
        raw=lesson.raw_text or "",
        title=subj.title if subj else None,
        lesson_type=subj.lesson_type if subj else None,
        teacher=subj.teacher.full_name if (subj and subj.teacher) else None,
        room=lesson.room.name if lesson.room else None,
        subgroup=subj.subgroup if subj else None,
        start_time=slot.start_time if slot else None,
        end_time=slot.end_time if slot else None,
        subject_id=lesson.subject_id if lesson else None,
    )


def _group_into_days(lessons: list[Lesson]) -> list[DaySchedule]:
    day_map: dict[date, DaySchedule] = {}
    for l in lessons:
        d = l.day.date
        if d not in day_map:
            day_map[d] = DaySchedule(date=d)
        day_map[d].lessons.append(_lesson_to_domain(l))
    return [day_map[d] for d in sorted(day_map)]


def get_today(group_id: int, target_date: Optional[date] = None) -> list[DaySchedule]:
    if target_date is None:
        target_date = date.today()
    with get_session() as session:
        lessons = sr.get_lessons_for_date(session, group_id, target_date)
    return _group_into_days(lessons)


def get_tomorrow(group_id: int) -> list[DaySchedule]:
    return get_today(group_id, target_date=date.today() + timedelta(days=1))


def get_week(group_id: int, start: Optional[date] = None) -> list[DaySchedule]:
    if start is None:
        today = date.today()
        start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    with get_session() as session:
        lessons = sr.get_lessons_for_date_range(session, group_id, start, end)
    return _group_into_days(lessons)


def get_two_weeks(group_id: int) -> list[DaySchedule]:
    start = date.today()
    end = start + timedelta(days=13)
    with get_session() as session:
        lessons = sr.get_lessons_for_date_range(session, group_id, start, end)
    return _group_into_days(lessons)

def get_next_week(group_id: int, start: Optional[date] = None) -> list[DaySchedule]:
    if start is None:
        today = date.today()
        start = today - timedelta(days=today.weekday() - 7)
    end = start + timedelta(days=6)
    with get_session() as session:
        lessons = sr.get_lessons_for_date_range(session, group_id, start, end)
    return _group_into_days(lessons)


def get_next_lessons_day(
    group_id: int,
    from_date: date,
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
    filters: Optional[SubjectFilters] = None,
    max_days: int = 21,
) -> Optional[DaySchedule]:
    """Find the nearest future day (after from_date) that has visible lessons."""
    for i in range(1, max_days + 1):
        target = from_date + timedelta(days=i)
        days = get_today(group_id, target_date=target)
        if days and has_visible_lessons(days[0], user_subgroup, display_mode, filters):
            return days[0]
    return None


def get_unique_subjects(group_id: int) -> list[tuple[str, Optional[str]]]:
    """Return distinct (title, lesson_type) pairs for a group's schedule."""
    with get_session() as session:
        return sr.get_unique_subjects_for_group(session, group_id)
