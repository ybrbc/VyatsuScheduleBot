"""Diff service: compare old and new lesson sets, classify changes.

Change types:
  ADDED   — lesson is in new but not in old
  REMOVED — lesson was in old but not in new
  CHANGED — same date+time+subject identity but room or teacher differs
  MOVED   — same date+subject but different time slot
"""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import date, time
from dataclasses import dataclass
from typing import Optional

from models.domain import ChangeType, LessonData, LessonSnapshot, ScheduleChange

logger = logging.getLogger(__name__)


def _snapshot(lesson: LessonData) -> LessonSnapshot:
    return LessonSnapshot(
        title=lesson.title,
        lesson_type=lesson.lesson_type,
        teacher=lesson.teacher,
        room=lesson.room,
        subgroup=lesson.subgroup,
        start_time=lesson.start_time,
        end_time=lesson.end_time,
    )


# A lesson is identified by (date, start_time, title, lesson_type, subgroup).
# Differences in room or teacher on the same slot = CHANGED.
# Same subject on same date but different slot = MOVED.
@dataclass(frozen=True)
class _SlotKey:
    """Uniquely identifies a lesson slot for comparison."""
    lesson_date: date
    start_time: Optional[time]
    title: Optional[str]
    lesson_type: Optional[str]
    subgroup: Optional[str]


@dataclass(frozen=True)
class _SubjectKey:
    """Identifies a subject without time — used for MOVED detection."""
    lesson_date: date
    title: Optional[str]
    lesson_type: Optional[str]
    subgroup: Optional[str]


def _slot_key(lesson: LessonData) -> _SlotKey:
    return _SlotKey(
        lesson_date=getattr(lesson, "_date", None),  # set by caller
        start_time=lesson.start_time,
        title=lesson.title,
        lesson_type=lesson.lesson_type,
        subgroup=lesson.subgroup,
    )


def calculate_diff(
    old_lessons: list[LessonData],
    new_lessons: list[LessonData],
) -> list[ScheduleChange]:
    """Return a list of ScheduleChange between two lesson sets.

    Both lists should have their `_date` attribute set (or use a tagged subclass).
    In practice, LessonData keeps `start_time`/`end_time` but the *date* comes
    from the DaySchedule wrapper.  The schedule_updater passes lessons already
    tagged with the date via the `_date` attribute.
    """
    changes: list[ScheduleChange] = []

    # Build lookup maps
    old_by_slot: dict[_SlotKey, LessonData] = {}
    new_by_slot: dict[_SlotKey, LessonData] = {}

    for l in old_lessons:
        k = _slot_key(l)
        if k.lesson_date is not None:
            old_by_slot[k] = l

    for l in new_lessons:
        k = _slot_key(l)
        if k.lesson_date is not None:
            new_by_slot[k] = l

    # Subjects without time slot (for MOVED detection)
    old_by_subject: dict[_SubjectKey, LessonData] = {}
    new_by_subject: dict[_SubjectKey, LessonData] = {}
    for k, l in old_by_slot.items():
        sk = _SubjectKey(k.lesson_date, k.title, k.lesson_type, k.subgroup)
        old_by_subject[sk] = l
    for k, l in new_by_slot.items():
        sk = _SubjectKey(k.lesson_date, k.title, k.lesson_type, k.subgroup)
        new_by_subject[sk] = l

    already_moved: set[_SlotKey] = set()

    # --- ADDED and CHANGED ---
    for key, new_l in new_by_slot.items():
        if key in old_by_slot:
            old_l = old_by_slot[key]
            # Same slot: check if anything changed
            if old_l.room != new_l.room or old_l.teacher != new_l.teacher:
                changes.append(ScheduleChange(
                    change_type=ChangeType.CHANGED,
                    lesson_date=key.lesson_date,
                    old_lesson=_snapshot(old_l),
                    new_lesson=_snapshot(new_l),
                ))
        else:
            # Not found at same slot — could be MOVED or truly ADDED
            sk = _SubjectKey(key.lesson_date, key.title, key.lesson_type, key.subgroup)
            if sk in old_by_subject:
                # Subject existed on same date at different time → MOVED
                old_l = old_by_subject[sk]
                old_key = _slot_key(old_l)
                changes.append(ScheduleChange(
                    change_type=ChangeType.MOVED,
                    lesson_date=key.lesson_date,
                    old_lesson=_snapshot(old_l),
                    new_lesson=_snapshot(new_l),
                ))
                already_moved.add(old_key)
            else:
                changes.append(ScheduleChange(
                    change_type=ChangeType.ADDED,
                    lesson_date=key.lesson_date,
                    old_lesson=None,
                    new_lesson=_snapshot(new_l),
                ))

    # --- REMOVED ---
    for key, old_l in old_by_slot.items():
        if key not in new_by_slot and key not in already_moved:
            sk = _SubjectKey(key.lesson_date, key.title, key.lesson_type, key.subgroup)
            if sk not in new_by_subject:
                # Truly removed (not just moved)
                changes.append(ScheduleChange(
                    change_type=ChangeType.REMOVED,
                    lesson_date=key.lesson_date,
                    old_lesson=_snapshot(old_l),
                    new_lesson=None,
                ))

    # Sort: by date, then by start time
    def _sort_key(c: ScheduleChange):
        snap = c.new_lesson or c.old_lesson
        t = snap.start_time if snap else None
        return (c.lesson_date, t or time(0, 0))

    changes.sort(key=_sort_key)

    logger.info("Diff: %d changes found", len(changes))
    return changes


def tag_lessons_with_date(days) -> list[LessonData]:
    """Flatten DaySchedule list into a tagged LessonData list for diffing.

    Sets the private `_date` attribute on each LessonData.
    """
    result: list[LessonData] = []
    for day in days:
        for lesson in day.lessons:
            lesson._date = day.date   # type: ignore[attr-defined]
            result.append(lesson)
    return result
