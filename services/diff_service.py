"""Diff service: compare old and new lesson sets, classify changes.

Root fix: the old algorithm keyed lessons by (date, time, title, type, subgroup)
using a plain dict — so multiple parallel lessons with the same subject but
different teachers (e.g. two Физкультура groups) silently overwrote each other,
producing spurious CHANGED events on unchanged schedules.

New algorithm:
  Step 1. Group lessons by (date, start_time) into lists — preserving all
          parallel lessons at the same slot.
  Step 2. Within each slot, identify each lesson by its full signature:
            (title, lesson_type, teacher, subgroup)
          — teacher is part of the identity, so two different teachers at
            the same time are correctly treated as two independent lessons.
  Step 3. Compare signatures:
            same sig + same room  → no change
            same sig + diff room  → CHANGED (room)
            only in new           → ADDED
            only in old           → REMOVED
  Step 4. Post-process REMOVED + ADDED at the *same slot* with the same
          (title, type, subgroup) but *different teacher* → CHANGED (teacher).
          Only when counts are 1:1 (unambiguous substitution).
  Step 5. Post-process remaining REMOVED + ADDED on the *same date* with the
          same full signature (title, type, teacher, subgroup) but different
          time → MOVED.
"""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import date, time
from dataclasses import dataclass
from typing import Optional

from models.domain import ChangeType, LessonData, LessonSnapshot, ScheduleChange

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Key types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TimeSlotKey:
    """Groups lessons that occur at the exact same time on the same day."""
    lesson_date: date
    start_time: Optional[time]


@dataclass(frozen=True)
class _LessonSig:
    """Full identity of a lesson within a slot (teacher included)."""
    title: Optional[str]
    lesson_type: Optional[str]
    teacher: Optional[str]
    subgroup: Optional[str]


@dataclass(frozen=True)
class _SubjectSig:
    """Subject identity without teacher — used for teacher-substitution detection."""
    lesson_date: date
    start_time: Optional[time]
    title: Optional[str]
    lesson_type: Optional[str]
    subgroup: Optional[str]


@dataclass(frozen=True)
class _MoveSig:
    """Full lesson identity without time — used for MOVED detection."""
    lesson_date: date
    title: Optional[str]
    lesson_type: Optional[str]
    teacher: Optional[str]
    subgroup: Optional[str]


# ---------------------------------------------------------------------------
# Main diff function
# ---------------------------------------------------------------------------

def calculate_diff(
    old_lessons: list[LessonData],
    new_lessons: list[LessonData],
) -> list[ScheduleChange]:
    """Return structured changes between two tagged lesson lists.

    Each lesson must have the _date attribute set (via tag_lessons_with_date).
    """
    changes: list[ScheduleChange] = []

    # ── Step 1: group by time slot ────────────────────────────────────────
    old_slots: dict[_TimeSlotKey, list[LessonData]] = defaultdict(list)
    new_slots: dict[_TimeSlotKey, list[LessonData]] = defaultdict(list)

    for l in old_lessons:
        d = getattr(l, "_date", None)
        if d is not None:
            old_slots[_TimeSlotKey(d, l.start_time)].append(l)

    for l in new_lessons:
        d = getattr(l, "_date", None)
        if d is not None:
            new_slots[_TimeSlotKey(d, l.start_time)].append(l)

    # Pending REMOVED and ADDED for post-processing
    pending_removed: list[tuple[_TimeSlotKey, LessonData]] = []
    pending_added:   list[tuple[_TimeSlotKey, LessonData]] = []

    # ── Step 2 + 3: compare each slot ────────────────────────────────────
    all_keys = set(old_slots) | set(new_slots)
    for slot_key in all_keys:
        old_group = old_slots.get(slot_key, [])
        new_group = new_slots.get(slot_key, [])

        old_by_sig: dict[_LessonSig, LessonData] = {}
        for l in old_group:
            sig = _LessonSig(l.title, l.lesson_type, l.teacher, l.subgroup)
            old_by_sig[sig] = l  # OK: (title, type, teacher, subgroup) is unique per DB row

        new_by_sig: dict[_LessonSig, LessonData] = {}
        for l in new_group:
            sig = _LessonSig(l.title, l.lesson_type, l.teacher, l.subgroup)
            new_by_sig[sig] = l

        for sig, new_l in new_by_sig.items():
            if sig in old_by_sig:
                old_l = old_by_sig[sig]
                if old_l.room != new_l.room:          # same teacher, different room
                    changes.append(ScheduleChange(
                        ChangeType.CHANGED, slot_key.lesson_date,
                        _snapshot(old_l), _snapshot(new_l),
                    ))
                # else: identical → no change
            else:
                pending_added.append((slot_key, new_l))

        for sig, old_l in old_by_sig.items():
            if sig not in new_by_sig:
                pending_removed.append((slot_key, old_l))

    # ── Step 4: teacher-substitution detection ────────────────────────────
    # Group pending by (date, time, title, type, subgroup)
    rem_by_subj: dict[_SubjectSig, list[tuple[_TimeSlotKey, LessonData]]] = defaultdict(list)
    add_by_subj: dict[_SubjectSig, list[tuple[_TimeSlotKey, LessonData]]] = defaultdict(list)

    for (sk, l) in pending_removed:
        rem_by_subj[_SubjectSig(sk.lesson_date, sk.start_time, l.title, l.lesson_type, l.subgroup)].append((sk, l))
    for (sk, l) in pending_added:
        add_by_subj[_SubjectSig(sk.lesson_date, sk.start_time, l.title, l.lesson_type, l.subgroup)].append((sk, l))

    merged_removed: set[int] = set()   # indices into pending_removed
    merged_added:   set[int] = set()   # indices into pending_added

    # Build index for fast lookup
    rem_idx = {id(l): i for i, (_, l) in enumerate(pending_removed)}
    add_idx = {id(l): i for i, (_, l) in enumerate(pending_added)}

    for subj_sig, rem_entries in rem_by_subj.items():
        add_entries = add_by_subj.get(subj_sig, [])
        # 1-to-1 unambiguous substitution only
        if len(rem_entries) == 1 and len(add_entries) == 1:
            _, old_l = rem_entries[0]
            _, new_l = add_entries[0]
            changes.append(ScheduleChange(
                ChangeType.CHANGED, subj_sig.lesson_date,
                _snapshot(old_l), _snapshot(new_l),
            ))
            merged_removed.add(rem_idx[id(old_l)])
            merged_added.add(add_idx[id(new_l)])

    # Residual after teacher-substitution matching
    residual_removed = [(sk, l) for i, (sk, l) in enumerate(pending_removed)
                        if i not in merged_removed]
    residual_added   = [(sk, l) for i, (sk, l) in enumerate(pending_added)
                        if i not in merged_added]

    # ── Step 5: MOVED detection ───────────────────────────────────────────
    rem_by_move: dict[_MoveSig, tuple[_TimeSlotKey, LessonData]] = {}
    for (sk, l) in residual_removed:
        mv = _MoveSig(sk.lesson_date, l.title, l.lesson_type, l.teacher, l.subgroup)
        rem_by_move[mv] = (sk, l)

    matched_moved_rem: set[int] = set()
    matched_moved_add: set[int] = set()

    res_rem_idx = {id(l): i for i, (_, l) in enumerate(residual_removed)}

    for i, (add_sk, add_l) in enumerate(residual_added):
        mv = _MoveSig(add_sk.lesson_date, add_l.title, add_l.lesson_type,
                      add_l.teacher, add_l.subgroup)
        if mv in rem_by_move:
            rem_sk, rem_l = rem_by_move[mv]
            changes.append(ScheduleChange(
                ChangeType.MOVED, add_sk.lesson_date,
                _snapshot(rem_l), _snapshot(add_l),
            ))
            matched_moved_rem.add(res_rem_idx[id(rem_l)])
            matched_moved_add.add(i)

    # ── Emit remaining ADDED and REMOVED ─────────────────────────────────
    for i, (sk, l) in enumerate(residual_removed):
        if i not in matched_moved_rem:
            changes.append(ScheduleChange(
                ChangeType.REMOVED, sk.lesson_date, _snapshot(l), None,
            ))

    for i, (sk, l) in enumerate(residual_added):
        if i not in matched_moved_add:
            changes.append(ScheduleChange(
                ChangeType.ADDED, sk.lesson_date, None, _snapshot(l),
            ))

    # ── Sort by date → start_time ─────────────────────────────────────────
    def _sort_key(c: ScheduleChange):
        snap = c.new_lesson or c.old_lesson
        return (c.lesson_date, snap.start_time if snap else time(0, 0))

    changes.sort(key=_sort_key)

    logger.info("Diff: %d changes found", len(changes))
    return changes

# ---------------------------------------------------------------------------
# Tagging helper (used by schedule_updater)
# ---------------------------------------------------------------------------

def tag_lessons_with_date(days) -> list[LessonData]:
    """Flatten DaySchedule list into a tagged LessonData list (sets _date attribute)."""
    result: list[LessonData] = []
    for day in days:
        for lesson in day.lessons:
            lesson._date = day.date   # type: ignore[attr-defined]
            result.append(lesson)
    return result
