"""Normalizer: parse a raw lesson string into structured fields.

Expected input formats:
  "Математика Лекция Подлевских М.Н. 14-202"
  "ФИб-1301-51-00 Математика Лекция Подлевских М.Н. 14-202"
  "ФИб-1301-51-00, 01 подгруппа ООП Лабораторная работа Шалагинова Н.В. 16-414"

Output: LessonData with individual fields populated.
"""
from __future__ import annotations
import re
import logging
from datetime import time
from typing import Optional

from models.domain import LessonData

logger = logging.getLogger(__name__)

# Known lesson types — sorted longest first to avoid partial matches
LESSON_TYPES: list[str] = sorted(
    [
        "Лабораторная работа",
        "Практическое занятие",
        "Контрольная работа",
        "Лекция",
        "Семинар",
        "Консультация",
        "Зачёт",
        "Экзамен",
        "Практика",
    ],
    key=len,
    reverse=True,
)

# Group name: starts with capital Cyrillic letters, then dash + digits pattern
# e.g. ФИб-1301-51-00, ЭЛб-2201-53-00
_GROUP_RE = re.compile(r"^([А-ЯЁ][А-ЯЁа-яё]+-\d+(?:-\d+){1,3})")

# Subgroup: ", 01 подгруппа" or "01 подгруппа" (any inflected form)
_SUBGROUP_RE = re.compile(r",?\s*(\d+)\s*подгруп\w*\s*", re.IGNORECASE)

# Teacher: "Фамилия И.О." — supports hyphenated surnames
_TEACHER_RE = re.compile(
    r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.[А-ЯЁ]\.)"
)

# Time slot: "08:20-09:55" or "08:20–09:55"
_TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})")


def parse_time(raw: str) -> tuple[Optional[time], Optional[time]]:
    """Extract start and end time from a time-cell string."""
    m = _TIME_RE.search(raw)
    if not m:
        return None, None
    try:
        h1, m1 = map(int, m.group(1).split(":"))
        h2, m2 = map(int, m.group(2).split(":"))
        return time(h1, m1), time(h2, m2)
    except ValueError:
        return None, None


def normalize_lesson(
    raw: str,
    default_group: Optional[str] = None,
    start_time: Optional[time] = None,
    end_time: Optional[time] = None,
) -> LessonData:
    """Parse *raw* lesson string into a LessonData.

    *default_group* is the group ID of the PDF being processed (used when the
    lesson text does not mention a group explicitly).
    """
    text = " ".join(raw.split())  # normalise whitespace

    # Empty cell — happens for blank rows in the PDF
    if not text:
        return LessonData(raw=raw, start_time=start_time, end_time=end_time)

    # --- Find lesson type ---
    lesson_type: Optional[str] = None
    type_pos = -1
    for lt in LESSON_TYPES:
        pos = text.find(lt)
        if pos >= 0 and (type_pos < 0 or pos < type_pos):
            lesson_type = lt
            type_pos = pos

    if lesson_type is None:
        # Cannot split on type; store whole text as title
        return LessonData(
            raw=raw,
            title=text,
            lesson_type=None,
            start_time=start_time,
            end_time=end_time,
            group_name=default_group,
        )

    left = text[:type_pos].strip()
    right = text[type_pos + len(lesson_type):].strip()

    # --- Parse right side: teacher + room ---
    teacher: Optional[str] = None
    room: Optional[str] = None

    teacher_match = _TEACHER_RE.search(right)
    if teacher_match:
        teacher = teacher_match.group(1).strip()
        after = right[teacher_match.end():].strip()
        if after:
            # Everything after teacher is room (take last token)
            room = after.split()[-1]
    else:
        # No teacher found — last token might be room
        tokens = right.split()
        if tokens:
            room = tokens[-1]

    # --- Parse left side: group + subgroup + title ---
    group_name: Optional[str] = default_group
    subgroup: Optional[str] = None
    remaining = left

    group_m = _GROUP_RE.match(remaining)
    if group_m:
        group_name = group_m.group(1).strip()
        remaining = remaining[group_m.end():].strip()

        subgroup_m = _SUBGROUP_RE.match(remaining)
        if subgroup_m:
            subgroup = subgroup_m.group(1)
            remaining = remaining[subgroup_m.end():].strip()
        elif remaining.startswith(","):
            remaining = remaining[1:].strip()

    title = remaining.strip() or None

    return LessonData(
        raw=raw,
        title=title,
        lesson_type=lesson_type,
        teacher=teacher,
        room=room,
        subgroup=subgroup,
        group_name=group_name,
        start_time=start_time,
        end_time=end_time,
    )
