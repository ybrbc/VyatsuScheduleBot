"""Pure-Python domain models — no DB or Telegram dependency."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Lesson / Schedule
# ---------------------------------------------------------------------------

@dataclass
class LessonData:
    """Single parsed lesson from the PDF or DB."""
    raw: str
    title: Optional[str] = None
    lesson_type: Optional[str] = None
    teacher: Optional[str] = None
    room: Optional[str] = None
    subgroup: Optional[str] = None
    group_name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    # DB subject ID — populated when loading from DB, None when parsing PDF
    subject_id: Optional[int] = None

    @property
    def time_label(self) -> str:
        if self.start_time and self.end_time:
            return (
                f"{self.start_time.strftime('%H:%M')}–"
                f"{self.end_time.strftime('%H:%M')}"
            )
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
    semester: int
    academic_year: str
    days: list[DaySchedule] = field(default_factory=list)

    @property
    def total_lessons(self) -> int:
        return sum(len(d.lessons) for d in self.days)



@dataclass
class SubjectInfo:
    """Lightweight view of a subjects table row for display in filter menus.
    SubjectInfo — a rich description of a Subject row used in filter UIs
    """
    id: int
    title: Optional[str]
    lesson_type: Optional[str]
    teacher_name: Optional[str]
    subgroup: Optional[str]

    def short_label(self, title_len: int = 22) -> str:
        """Compact one-line label for an inline button."""
        _TYPE_SHORT = {
            "Лабораторная работа":  "Лаба",
            "Практическое занятие": "Практика",
            "Лекция":               "Лекция",
            "Семинар":              "Семинар",
            "Консультация":         "Консульт.",
            "Контрольная работа":   "Контр.",
            "Зачёт":                "Зачёт",
            "Экзамен":              "Экзамен",
        }
        parts: list[str] = []
        if self.title:
            parts.append(self.title[:title_len])
        if self.lesson_type:
            parts.append(_TYPE_SHORT.get(self.lesson_type, self.lesson_type[:6]))
        if self.subgroup:
            parts.append(f"пд.{self.subgroup}")
        if self.teacher_name:
            # Surname only
            surname = self.teacher_name.split()[0]
            parts.append(surname[:14])
        return " / ".join(parts)

    def full_label(self) -> str:
        """Multi-part description for a filter list entry."""
        parts: list[str] = []
        if self.title:
            parts.append(self.title)
        if self.lesson_type:
            parts.append(self.lesson_type)
        if self.subgroup:
            parts.append(f"подгр. {self.subgroup}")
        if self.teacher_name:
            parts.append(self.teacher_name)
        return " · ".join(parts) if parts else f"subject #{self.id}"


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

class ChangeType(str, Enum):
    ADDED   = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"
    MOVED   = "MOVED"


@dataclass
class LessonSnapshot:
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
            return (
                f"{self.start_time.strftime('%H:%M')}–"
                f"{self.end_time.strftime('%H:%M')}"
            )
        return "?"


@dataclass
class ScheduleChange:
    change_type: ChangeType
    lesson_date: date
    old_lesson: Optional[LessonSnapshot] = None
    new_lesson: Optional[LessonSnapshot] = None

    def time_label(self) -> str:
        snap = self.new_lesson or self.old_lesson
        return snap.time_label if snap else "?"
