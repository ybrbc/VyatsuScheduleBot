"""Repository queries for subject progress."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.models import (
    Lesson,
    ScheduleDay,
    SchedulePeriod,
    Subject,
    SubjectProgressTarget,
    TimeSlot,
)


def get_targets(
    session: Session,
    group_id: int,
    user_subgroup: str | None,
) -> list[SubjectProgressTarget]:
    """Return configured progress targets visible to the selected subgroup."""
    query = session.query(SubjectProgressTarget).filter_by(group_id=group_id)

    if user_subgroup:
        query = query.filter(
            or_(
                SubjectProgressTarget.subgroup == "",
                SubjectProgressTarget.subgroup == user_subgroup,
            )
        )

    return (
        query
        .order_by(
            SubjectProgressTarget.title,
            SubjectProgressTarget.lesson_type,
            SubjectProgressTarget.subgroup,
        )
        .all()
    )


def get_completed_lesson_counts(
    session: Session,
    group_id: int,
    now: datetime,
) -> dict[tuple[str, str, str], int]:
    """Return completed pair counts keyed by title/type/subgroup.

    A lesson is completed only after its time slot has ended.  Teacher is
    intentionally absent from the key.  Rows that share the same date and
    time slot are grouped so a teacher change (or duplicate teacher rows)
    cannot count the same pair twice.
    """
    today = now.date()
    current_time = now.time().replace(tzinfo=None)

    rows = (
        session.query(
            Subject.title,
            Subject.lesson_type,
            Subject.subgroup,
            ScheduleDay.date,
            Lesson.time_slot_id,
        )
        .join(Lesson, Lesson.subject_id == Subject.id)
        .join(ScheduleDay, Lesson.day_id == ScheduleDay.id)
        .join(SchedulePeriod, ScheduleDay.period_id == SchedulePeriod.id)
        .join(TimeSlot, Lesson.time_slot_id == TimeSlot.id)
        .filter(
            SchedulePeriod.group_id == group_id,
            Subject.title.isnot(None),
            Subject.lesson_type.isnot(None),
            or_(
                ScheduleDay.date < today,
                and_(
                    ScheduleDay.date == today,
                    TimeSlot.end_time <= current_time,
                ),
            ),
        )
        .group_by(
            Subject.title,
            Subject.lesson_type,
            Subject.subgroup,
            ScheduleDay.date,
            Lesson.time_slot_id,
        )
        .all()
    )

    result: dict[tuple[str, str, str], int] = {}
    for title, lesson_type, subgroup, _lesson_date, _slot_id in rows:
        key = (title, lesson_type, subgroup or "")
        result[key] = result.get(key, 0) + 1
    return result
