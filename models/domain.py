"""Pure-Python domain models.
These are data containers passed between Parser, Services and Repositories.
They have NO dependency on SQLAlchemy or Telegram.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time, date
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Lesson / Schedule
# ---------------------------------------------------------------------------

@dataclass
class LessonData:
    """Single parsed lesson from the PDF."""
    raw: str                        # original unparsed string
    title: Optional[str] = None
    lesson_type: Optional[str] = None
    teacher: Optional[str] = None
    room: Optional[str] = None
    subgroup: Optional[str] = None  # "01", "02", or None
    group_name: Optional[str] = None  # group name if listed in lesson text
    start_time: Optional[time] = None
    end_time: Optional[time] = None

    @property
    def time_label(self) -> str:
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%H:%M')}–{self.end_time.strftime('%H:%M')}"
        return ""


@dataclass
class DaySchedule:
    date: date
    lessons: list[LessonData] = field(default_factory=list)


@dataclass
class GroupSchedule:
    group_external_id: str
    days: list[DaySchedule] = field(default_factory=list)


@dataclass
class Schedule:
    """Result of parsing a single PDF file."""
    group_external_id: str
    period_start: date
    period_end: date
    semester: int           # 1 or 2
    academic_year: str      # "2026-2027"
    days: list[DaySchedule] = field(default_factory=list)

    @property
    def total_lessons(self) -> int:
        return sum(len(d.lessons) for d in self.days)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"
    MOVED = "MOVED"


@dataclass
class LessonSnapshot:
    """Compact lesson description for diff output."""
    title: Optional[str]
    lesson_type: Optional[str]
    teacher: Optional[str]
    room: Optional[str]
    subgroup: Optional[str]
    start_time: Optional[time]
    end_time: Optional[time]

    @property
    def time_label(self) -> str:
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%H:%M')}–{self.end_time.strftime('%H:%M')}"
        return "?"


@dataclass
class ScheduleChange:
    """One atomic change in the schedule."""
    change_type: ChangeType
    lesson_date: date
    old_lesson: Optional[LessonSnapshot] = None
    new_lesson: Optional[LessonSnapshot] = None

    def time_label(self) -> str:
        if self.new_lesson and self.new_lesson.time_label:
            return self.new_lesson.time_label
        if self.old_lesson and self.old_lesson.time_label:
            return self.old_lesson.time_label
        return "?"
