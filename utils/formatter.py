"""Format schedule and diff objects for Telegram (HTML parse mode).

Display modes for other-subgroup lessons:
  hide                  — omit completely (default)
  strikethrough         — <s>text</s>
  spoiler               — <tg-spoiler>text</tg-spoiler>
  spoiler_strikethrough — <tg-spoiler><s>text</s></tg-spoiler>
    (appears hidden; after tap shows as strikethrough)

Diff display modes for other-subgroup changes in notifications:
  hide                  — omit completely
  inline_strikethrough  — show in same message, strikethrough
  inline_spoiler        — show in same message, spoiler
  separate              — caller sends a second message
"""
from __future__ import annotations
from datetime import date
from typing import Optional

from models.domain import DaySchedule, LessonData, ScheduleChange, ChangeType

_DAYS_RU = (
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
)
_MONTHS_RU = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_date_header(d: date) -> str:
    return f"{d.day} {_MONTHS_RU[d.month]} {d.year} ({_DAYS_RU[d.weekday()]})"


# ---------------------------------------------------------------------------
# Display-mode wrappers
# ---------------------------------------------------------------------------

def _wrap(text: str, mode: str) -> Optional[str]:
    """Wrap text in the appropriate Telegram HTML for the display mode.
    Returns None for 'hide' (caller should skip the lesson).
    """
    if mode == "hide":
        return None
    if mode == "strikethrough":
        return f"<s>{text}</s>"
    if mode == "spoiler":
        return f"<tg-spoiler>{text}</tg-spoiler>"
    if mode == "spoiler_strikethrough":
        return f"<tg-spoiler><s>{text}</s></tg-spoiler>"
    return text  # unknown mode → show normally


def _is_other_subgroup(lesson: LessonData, user_subgroup: Optional[str]) -> bool:
    return bool(
        user_subgroup
        and lesson.subgroup
        and lesson.subgroup != user_subgroup
    )


# ---------------------------------------------------------------------------
# Lesson formatting
# ---------------------------------------------------------------------------

def _lesson_body(lesson: LessonData, show_subgroup: bool = True) -> str:
    """Raw HTML for a single lesson (no time header)."""
    lines: list[str] = []
    if lesson.title:
        lines.append(f"📚 {_esc(lesson.title)}")
    if lesson.lesson_type:
        sg = f" (подгр. {lesson.subgroup})" if lesson.subgroup and show_subgroup else ""
        lines.append(f"🔬 {_esc(lesson.lesson_type)}{sg}")
    if lesson.teacher:
        lines.append(f"👨‍🏫 {_esc(lesson.teacher)}")
    if lesson.room:
        lines.append(f"🏫 {_esc(lesson.room)}")
    return "\n".join(lines)


def fmt_lesson(
    lesson: LessonData,
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
    show_time: bool = True,
) -> Optional[str]:
    """Format one lesson. Returns None if it should be hidden entirely."""
    lines: list[str] = []
    if show_time and lesson.start_time and lesson.end_time:
        lines.append(
            f"<b>{lesson.start_time.strftime('%H:%M')}–"
            f"{lesson.end_time.strftime('%H:%M')}</b>"
        )

    body = _lesson_body(lesson)
    if not body:
        return None

    if _is_other_subgroup(lesson, user_subgroup):
        wrapped = _wrap(body, display_mode)
        if wrapped is None:
            return None
        lines.append(wrapped)
    else:
        lines.append(body)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Day / multi-day formatting
# ---------------------------------------------------------------------------

def fmt_day(
    day: DaySchedule,
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
) -> str:
    header = f"<b>{fmt_date_header(day.date)}</b>"
    if not day.lessons:
        return f"{header}\n<i>Пар нет</i>"

    blocks: list[str] = []
    for lesson in day.lessons:
        text = fmt_lesson(lesson, user_subgroup, display_mode)
        if text:
            blocks.append(text)

    if not blocks:
        return f"{header}\n<i>Пар нет (для вашей подгруппы)</i>"

    return header + "\n\n" + "\n\n".join(blocks)


def fmt_days(
    days: list[DaySchedule],
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
) -> str:
    if not days:
        return "<i>Расписание не найдено.</i>"
    sep = "\n\n" + "─" * 20 + "\n\n"
    return sep.join(fmt_day(d, user_subgroup, display_mode) for d in days)


# ---------------------------------------------------------------------------
# Diff formatting
# ---------------------------------------------------------------------------

_CHANGE_ICON = {
    ChangeType.ADDED:   "✅",
    ChangeType.REMOVED: "❌",
    ChangeType.CHANGED: "✏️",
    ChangeType.MOVED:   "🔀",
}


def _snap_line(snap) -> str:
    if snap is None:
        return "—"
    parts: list[str] = []
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
    return " · ".join(parts) or "—"


def _fmt_one_change(ch: ScheduleChange) -> str:
    icon = _CHANGE_ICON.get(ch.change_type, "❓")
    t = ch.time_label()
    if ch.change_type == ChangeType.ADDED:
        return f"{icon} <b>{t}</b> — {_snap_line(ch.new_lesson)}"
    if ch.change_type == ChangeType.REMOVED:
        return f"{icon} <b>{t}</b> — <s>{_snap_line(ch.old_lesson)}</s>"
    if ch.change_type == ChangeType.CHANGED:
        return (
            f"{icon} <b>{t}</b>\n"
            f"  Было: <s>{_snap_line(ch.old_lesson)}</s>\n"
            f"  Стало: {_snap_line(ch.new_lesson)}"
        )
    if ch.change_type == ChangeType.MOVED:
        old_t = ch.old_lesson.time_label if ch.old_lesson else "?"
        return (
            f"{icon} {_snap_line(ch.new_lesson)}\n"
            f"  {old_t} → {t}"
        )
    return f"{icon} {_snap_line(ch.new_lesson or ch.old_lesson)}"


def _split_changes_by_subgroup(
    changes: list[ScheduleChange],
    user_subgroup: Optional[str],
) -> tuple[list[ScheduleChange], list[ScheduleChange]]:
    """Split into (my_subgroup_changes, other_subgroup_changes)."""
    if not user_subgroup:
        return changes, []

    mine, other = [], []
    for ch in changes:
        snap = ch.new_lesson or ch.old_lesson
        sg = snap.subgroup if snap else None
        if sg is None or sg == user_subgroup:
            mine.append(ch)
        else:
            other.append(ch)
    return mine, other


def fmt_changes(
    changes: list[ScheduleChange],
    user_subgroup: Optional[str] = None,
    diff_display_mode: str = "hide",
) -> tuple[str, Optional[str]]:
    """Format change notifications.

    Returns (main_message, optional_second_message).
    second_message is non-None only when diff_display_mode == 'separate'.
    """
    if not changes:
        return "<i>Изменений нет.</i>", None

    mine, other = _split_changes_by_subgroup(changes, user_subgroup)

    def _build_message(ch_list: list[ScheduleChange], title: str) -> str:
        by_date: dict[date, list[ScheduleChange]] = {}
        for c in ch_list:
            by_date.setdefault(c.lesson_date, []).append(c)

        parts = [f"<b>{title}</b>"]
        for d in sorted(by_date):
            parts.append(f"\n<b>{fmt_date_header(d)}</b>")
            for ch in by_date[d]:
                parts.append(_fmt_one_change(ch))
        return "\n".join(parts)

    # Build main message (always for user's subgroup)
    main_parts: list[str] = []
    if mine:
        main_parts.append(_build_message(mine, "📣 Изменения в расписании"))

    # Handle other subgroup
    second_msg: Optional[str] = None
    if other and diff_display_mode != "hide":
        if diff_display_mode == "separate":
            second_msg = _build_message(other, "📣 Изменения (другая подгруппа)")
        else:
            # Wrap each change line
            other_lines: list[str] = ["\n<i>Другая подгруппа:</i>"]
            for ch in other:
                line = _fmt_one_change(ch)
                if diff_display_mode == "inline_strikethrough":
                    line = f"<s>{line}</s>"
                elif diff_display_mode == "inline_spoiler":
                    line = f"<tg-spoiler>{line}</tg-spoiler>"
                other_lines.append(line)
            main_parts.append("\n".join(other_lines))

    main_msg = "\n".join(main_parts) if main_parts else "<i>Изменений нет.</i>"
    return main_msg, second_msg


# ---------------------------------------------------------------------------
# Display mode labels (for UI)
# ---------------------------------------------------------------------------

DISPLAY_MODE_LABELS = {
    "hide": "🙈 Скрыть",
    "strikethrough": "~~Зачеркнуть~~",
    "spoiler": "👁 Спойлер",
    "spoiler_strikethrough": "👁+~~ Спойлер+зачерк.",
}

DIFF_DISPLAY_MODE_LABELS = {
    "hide": "🙈 Не показывать",
    "inline_strikethrough": "~~В сообщении (зачерк.)~~",
    "inline_spoiler": "👁 В сообщении (спойлер)",
    "separate": "📨 Отдельным сообщением",
}
