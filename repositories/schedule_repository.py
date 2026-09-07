"""Schedule repository."""
from __future__ import annotations
import logging
from datetime import date, time
from typing import Optional

from sqlalchemy.orm import Session, joinedload, contains_eager

from database.models import (
    Lesson, PdfHash, Room, ScheduleDay, SchedulePeriod,
    Subject, Teacher, TimeSlot,
)
from models.domain import DaySchedule, LessonData, Schedule, SubjectInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# get-or-create helpers
# ---------------------------------------------------------------------------

def _get_or_create_teacher(session: Session, name: Optional[str]) -> Optional[Teacher]:
    if not name:
        return None
    obj = session.query(Teacher).filter_by(full_name=name).first()
    if obj is None:
        obj = Teacher(full_name=name)
        session.add(obj); session.flush()
    return obj


def _get_or_create_subject(
    session, title, lesson_type, teacher, subgroup
) -> Optional[Subject]:
    tid = teacher.id if teacher else None
    obj = session.query(Subject).filter_by(
        title=title, lesson_type=lesson_type, teacher_id=tid, subgroup=subgroup
    ).first()
    if obj is None:
        obj = Subject(title=title, lesson_type=lesson_type, teacher_id=tid, subgroup=subgroup)
        session.add(obj); session.flush()
    return obj


def _get_or_create_room(session, name: Optional[str]) -> Optional[Room]:
    if not name:
        return None
    obj = session.query(Room).filter_by(name=name).first()
    if obj is None:
        obj = Room(name=name); session.add(obj); session.flush()
    return obj


def _get_or_create_timeslot(session, start, end) -> Optional[TimeSlot]:
    if start is None or end is None:
        return None
    obj = session.query(TimeSlot).filter_by(start_time=start, end_time=end).first()
    if obj is None:
        obj = TimeSlot(start_time=start, end_time=end); session.add(obj); session.flush()
    return obj


# ---------------------------------------------------------------------------
# Period management
# ---------------------------------------------------------------------------

def get_period(session, group_id, start, end) -> Optional[SchedulePeriod]:
    return session.query(SchedulePeriod).filter_by(
        group_id=group_id, start_date=start, end_date=end
    ).first()


def save_schedule(session: Session, group_id: int, schedule: Schedule) -> SchedulePeriod:
    period = get_period(session, group_id, schedule.period_start, schedule.period_end)
    if period:
        for day in list(period.days):
            session.delete(day)
        session.flush()
        period.semester = schedule.semester
        period.academic_year = schedule.academic_year
    else:
        period = SchedulePeriod(
            group_id=group_id, start_date=schedule.period_start,
            end_date=schedule.period_end, semester=schedule.semester,
            academic_year=schedule.academic_year,
        )
        session.add(period); session.flush()

    for day_data in schedule.days:
        day_obj = ScheduleDay(period_id=period.id, date=day_data.date)
        session.add(day_obj); session.flush()
        for ld in day_data.lessons:
            teacher = _get_or_create_teacher(session, ld.teacher)
            subject = _get_or_create_subject(session, ld.title, ld.lesson_type, teacher, ld.subgroup)
            room    = _get_or_create_room(session, ld.room)
            slot    = _get_or_create_timeslot(session, ld.start_time, ld.end_time)
            session.add(Lesson(
                day_id=day_obj.id,
                time_slot_id=slot.id    if slot    else None,
                subject_id=subject.id   if subject else None,
                room_id=room.id         if room    else None,
                raw_text=ld.raw,
            ))

    session.flush()
    logger.info(
        "Saved %s %s–%s (%d days, %d lessons)",
        group_id, schedule.period_start, schedule.period_end,
        len(schedule.days), schedule.total_lessons,
    )
    return period


# ---------------------------------------------------------------------------
# Hash tracking
# ---------------------------------------------------------------------------

def get_hash(session, group_id, start, end) -> Optional[str]:
    row = session.query(PdfHash).filter_by(
        group_id=group_id, period_start=start, period_end=end
    ).first()
    return row.hash if row else None


def upsert_hash(session, group_id, start, end, hash_val) -> None:
    row = session.query(PdfHash).filter_by(
        group_id=group_id, period_start=start, period_end=end
    ).first()
    if row:
        row.hash = hash_val
    else:
        session.add(PdfHash(group_id=group_id, period_start=start,
                            period_end=end, hash=hash_val))
    session.flush()


# ---------------------------------------------------------------------------
# Shared lesson → domain conversion
# ---------------------------------------------------------------------------

def _lesson_to_domain(l: Lesson) -> LessonData:
    subj = l.subject
    slot = l.time_slot
    return LessonData(
        raw=l.raw_text or "",
        title=subj.title          if subj else None,
        lesson_type=subj.lesson_type if subj else None,
        teacher=subj.teacher.full_name if (subj and subj.teacher) else None,
        room=l.room.name          if l.room else None,
        subgroup=subj.subgroup    if subj else None,
        start_time=slot.start_time if slot else None,
        end_time=slot.end_time    if slot else None,
        subject_id=subj.id        if subj else None,
    )


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def _base_query(session, group_id):
    """Return a base Lesson query joined to ScheduleDay/Period/TimeSlot."""
    return (
        session.query(Lesson)
        .join(ScheduleDay)
        .join(SchedulePeriod)
        .join(Lesson.time_slot)
        .filter(SchedulePeriod.group_id == group_id)
        .options(
            contains_eager(Lesson.time_slot),
            contains_eager(Lesson.day),
            joinedload(Lesson.subject).joinedload(Subject.teacher),
            joinedload(Lesson.room),
        )
    )


def get_lessons_for_date(session, group_id, target_date) -> list[Lesson]:
    return (
        _base_query(session, group_id)
        .filter(ScheduleDay.date == target_date)
        .order_by(TimeSlot.start_time)
        .all()
    )


def get_lessons_for_date_range(session, group_id, start, end) -> list[Lesson]:
    return (
        _base_query(session, group_id)
        .filter(ScheduleDay.date >= start, ScheduleDay.date <= end)
        .order_by(ScheduleDay.date, TimeSlot.start_time)
        .all()
    )


def get_period_as_domain_days(session, group_id, start, end) -> list[DaySchedule]:
    period = get_period(session, group_id, start, end)
    if not period:
        return []

    lessons = (
        session.query(Lesson)
        .join(ScheduleDay)
        .filter(ScheduleDay.period_id == period.id)
        .join(Lesson.time_slot)
        .options(
            contains_eager(Lesson.day),
            contains_eager(Lesson.time_slot),
            joinedload(Lesson.subject).joinedload(Subject.teacher),
            joinedload(Lesson.room),
        )
        .order_by(ScheduleDay.date, TimeSlot.start_time)
        .all()
    )

    day_map: dict[date, DaySchedule] = {}
    for l in lessons:
        d = l.day.date
        if d not in day_map:
            day_map[d] = DaySchedule(date=d)
        day_map[d].lessons.append(_lesson_to_domain(l))

    return [day_map[d] for d in sorted(day_map)]


# ---------------------------------------------------------------------------
# Subject list for filter UI
# ---------------------------------------------------------------------------

def get_subjects_for_group(session: Session, group_id: int) -> list[SubjectInfo]:
    """Return all distinct subjects used in this group's schedule as SubjectInfo objects.

    Sorted by title → lesson_type → subgroup → teacher for predictable display order.
    """
    rows = (
        session.query(Subject)
        .join(Lesson, Lesson.subject_id == Subject.id)
        .join(ScheduleDay, Lesson.day_id == ScheduleDay.id)
        .join(SchedulePeriod, ScheduleDay.period_id == SchedulePeriod.id)
        .filter(SchedulePeriod.group_id == group_id)
        .options(joinedload(Subject.teacher))
        .distinct()
        .order_by(Subject.title, Subject.lesson_type, Subject.subgroup)
        .all()
    )
    seen: set[int] = set()
    result: list[SubjectInfo] = []
    for s in rows:
        if s.id in seen:
            continue
        seen.add(s.id)
        result.append(SubjectInfo(
            id=s.id,
            title=s.title,
            lesson_type=s.lesson_type,
            teacher_name=s.teacher.full_name if s.teacher else None,
            subgroup=s.subgroup,
        ))
    return result


def get_unique_subjects_for_group(session, group_id) -> list[tuple]:
    """Legacy shim — kept for schedule_service.get_unique_subjects."""
    infos = get_subjects_for_group(session, group_id)
    return [(i.title, i.lesson_type) for i in infos]
