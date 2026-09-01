"""Format schedule and diff objects into Telegram-safe HTML."""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional

from models.domain import LessonData, DaySchedule, ScheduleChange, ChangeType

_DAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_MONTHS_RU = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _esc(text: str) -> str:
    """Escape HTML special chars."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_date_header(d: date) -> str:
    day_name = _DAYS_RU[d.weekday()]
    return f"{d.day} {_MONTHS_RU[d.month]} {d.year} ({day_name})"


def fmt_lesson(lesson: LessonData, *, show_subgroup: bool = True) -> str:
    """Format a single lesson as an HTML block."""
    lines: list[str] = []
    if lesson.start_time and lesson.end_time:
        lines.append(
            f"<b>{lesson.start_time.strftime('%H:%M')}–{lesson.end_time.strftime('%H:%M')}</b>"
        )
    if lesson.title:
        lines.append(f"📚 {_esc(lesson.title)}")
    if lesson.lesson_type:
        subg = f" (подгр. {lesson.subgroup})" if lesson.subgroup and show_subgroup else ""
        lines.append(f"🔬 {_esc(lesson.lesson_type)}{subg}")
    if lesson.teacher:
        lines.append(f"👨‍🏫 {_esc(lesson.teacher)}")
    if lesson.room:
        lines.append(f"🏫 {_esc(lesson.room)}")
    return "\n".join(lines)


def fmt_day(day: DaySchedule, *, user_subgroup: Optional[str] = None) -> str:
    """Format all lessons for one day."""
    if not day.lessons:
        return f"<i>{fmt_date_header(day.date)}</i>\n<i>Пар нет</i>"

    lessons = day.lessons
    if user_subgroup:
        # Keep lessons with matching subgroup OR no subgroup (common lectures)
        lessons = [l for l in lessons if not l.subgroup or l.subgroup == user_subgroup]

    header = f"<b>{fmt_date_header(day.date)}</b>"
    if not lessons:
        return f"{header}\n<i>Пар нет (для вашей подгруппы)</i>"

    blocks = [fmt_lesson(l) for l in lessons]
    return header + "\n\n" + "\n\n".join(blocks)


def fmt_days(days: list[DaySchedule], *, user_subgroup: Optional[str] = None) -> str:
    """Format multiple days."""
    if not days:
        return "<i>Расписание не найдено.</i>"
    sections = [fmt_day(d, user_subgroup=user_subgroup) for d in days]
    return "\n\n" + "—" * 20 + "\n\n".join(
        [""] + sections  # leading separator before first day
    )


# ---------------------------------------------------------------------------
# Diff formatting
# ---------------------------------------------------------------------------

def _snapshot_line(snap) -> str:
    if snap is None:
        return "—"
    parts = []
    if snap.title:
        parts.append(_esc(snap.title))
    if snap.lesson_type:
        parts.append(_esc(snap.lesson_type))
    if snap.subgroup:
        parts.append(f"подгр. {snap.subgroup}")
    if snap.teacher:
        parts.append(_esc(snap.teacher))
    if snap.room:
        parts.append(f"🏫 {_esc(snap.room)}")
    return " · ".join(parts) if parts else "—"


_CHANGE_ICON = {
    ChangeType.ADDED:   "✅",
    ChangeType.REMOVED: "❌",
    ChangeType.CHANGED: "✏️",
    ChangeType.MOVED:   "🔀",
}


def fmt_changes(changes: list[ScheduleChange]) -> str:
    """Format a list of ScheduleChange into a Telegram HTML message."""
    if not changes:
        return "<i>Изменений нет.</i>"

    # Group by date
    by_date: dict[date, list[ScheduleChange]] = {}
    for c in changes:
        by_date.setdefault(c.lesson_date, []).append(c)

    parts: list[str] = ["<b>📣 Изменения в расписании</b>\n"]
    for d in sorted(by_date):
        parts.append(f"\n<b>{fmt_date_header(d)}</b>")
        for ch in by_date[d]:
            icon = _CHANGE_ICON.get(ch.change_type, "❓")
            time_label = ch.time_label()
            if ch.change_type == ChangeType.ADDED:
                parts.append(f"{icon} <b>{time_label}</b> — {_snapshot_line(ch.new_lesson)}")
            elif ch.change_type == ChangeType.REMOVED:
                parts.append(f"{icon} <b>{time_label}</b> — <s>{_snapshot_line(ch.old_lesson)}</s>")
            elif ch.change_type == ChangeType.CHANGED:
                parts.append(
                    f"{icon} <b>{time_label}</b>\n"
                    f"  Было: <s>{_snapshot_line(ch.old_lesson)}</s>\n"
                    f"  Стало: {_snapshot_line(ch.new_lesson)}"
                )
            elif ch.change_type == ChangeType.MOVED:
                old_t = ch.old_lesson.time_label if ch.old_lesson else "?"
                new_t = ch.new_lesson.time_label if ch.new_lesson else "?"
                parts.append(
                    f"{icon} {_snapshot_line(ch.new_lesson)}\n"
                    f"  {old_t} → {new_t}"
                )

    return "\n".join(parts)
