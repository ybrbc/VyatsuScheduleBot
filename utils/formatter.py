"""Format schedule and diff for Telegram HTML.

Key features:
  - Same-time lessons grouped: time shown once, then all lesson bodies listed.
  - Subject filters applied before display:
      always_show → show regardless of subgroup / display_mode
      never_show  → hide completely
  - Display modes for other-subgroup lessons:
      hide | strikethrough | spoiler | spoiler_strikethrough
  - Diff display modes for other-subgroup changes:
      hide | inline_strikethrough | inline_spoiler | separate
"""
from __future__ import annotations
from datetime import date, time
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

# Type alias for filter dict
SubjectFilters = dict[int, str]  # subject_id → filter_type


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_date_header(d: date) -> str:
    return f"{d.day} {_MONTHS_RU[d.month]} {d.year} ({_DAYS_RU[d.weekday()]})"


# ---------------------------------------------------------------------------
# Display-mode wrappers
# ---------------------------------------------------------------------------

def _wrap(text: str, mode: str) -> Optional[str]:
    """Wrap text in Telegram HTML for the display mode.  Returns None for 'hide'."""
    if mode == "hide":
        return None
    if mode == "strikethrough":
        return f"<s>{text}</s>"
    if mode == "spoiler":
        return f"<tg-spoiler>{text}</tg-spoiler>"
    if mode == "spoiler_strikethrough":
        return f"<tg-spoiler><s>{text}</s></tg-spoiler>"
    return text


def _filter_type(lesson: LessonData, filters: SubjectFilters) -> Optional[str]:
    """Return 'always_show', 'never_show', or None for a lesson."""
    if not filters or lesson.subject_id is None:
        return None
    return filters.get(lesson.subject_id)


def _is_other_subgroup(lesson: LessonData, user_subgroup: Optional[str]) -> bool:
    return bool(user_subgroup and lesson.subgroup and lesson.subgroup != user_subgroup)


# ---------------------------------------------------------------------------
# Lesson body (without time header)
# ---------------------------------------------------------------------------

def _lesson_body(lesson: LessonData) -> str:
    lines: list[str] = []
    if lesson.title:
        lines.append(f"📚 {_esc(lesson.title)}")
    if lesson.lesson_type:
        sg = f" (подгр. {lesson.subgroup})" if lesson.subgroup else ""
        lines.append(f"🔬 {_esc(lesson.lesson_type)}{sg}")
    if lesson.teacher:
        lines.append(f"👨‍🏫 {_esc(lesson.teacher)}")
    if lesson.room:
        lines.append(f"🏫 {_esc(lesson.room)}")
    return "\n".join(lines)


def _render_lesson_body(
    lesson: LessonData,
    user_subgroup: Optional[str],
    display_mode: str,
    filters: SubjectFilters,
) -> Optional[str]:
    """Return formatted body or None if hidden."""
    ft = _filter_type(lesson, filters)

    if ft == "never_show":
        return None
    if ft == "always_show":
        return _lesson_body(lesson)  # always show, no wrapping

    body = _lesson_body(lesson)
    if not body:
        return None

    if _is_other_subgroup(lesson, user_subgroup):
        return _wrap(body, display_mode)

    return body


# ---------------------------------------------------------------------------
# Day formatting (time-grouped)
# ---------------------------------------------------------------------------

def fmt_day(
    day: DaySchedule,
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
    filters: Optional[SubjectFilters] = None,
) -> str:
    header = f"<b>{fmt_date_header(day.date)}</b>"
    if not day.lessons:
        return f"{header}\n<i>Пар нет</i>"

    _filters = filters or {}

    # Group lessons by (start_time, end_time)
    slot_order: list[tuple[Optional[time], Optional[time]]] = []
    slot_lessons: dict[tuple, list[LessonData]] = {}
    for lesson in day.lessons:
        key = (lesson.start_time, lesson.end_time)
        if key not in slot_lessons:
            slot_order.append(key)
            slot_lessons[key] = []
        slot_lessons[key].append(lesson)

    blocks: list[str] = []
    for key in slot_order:
        st, et = key
        lessons_in_slot = slot_lessons[key]

        # Render each lesson body
        bodies: list[str] = []
        for lesson in lessons_in_slot:
            body = _render_lesson_body(lesson, user_subgroup, display_mode, _filters)
            if body:
                bodies.append(body)

        if not bodies:
            continue

        # Time header shown once, then bodies separated by blank line
        if st and et:
            time_line = f"<b>{st.strftime('%H:%M')}–{et.strftime('%H:%M')}</b>"
            blocks.append(time_line + "\n" + "\n\n".join(bodies))
        else:
            blocks.append("\n\n".join(bodies))

    if not blocks:
        return f"{header}\n<i>Пар нет (для вашей подгруппы)</i>"

    return header + "\n\n" + "\n\n".join(blocks)


def fmt_days(
    days: list[DaySchedule],
    user_subgroup: Optional[str] = None,
    display_mode: str = "hide",
    filters: Optional[SubjectFilters] = None,
) -> str:
    if not days:
        return "<i>Расписание не найдено.</i>"
    sep = "\n\n" + "─" * 20 + "\n\n"
    return sep.join(fmt_day(d, user_subgroup, display_mode, filters) for d in days)


def has_visible_lessons(
    day: DaySchedule,
    user_subgroup: Optional[str],
    display_mode: str,
    filters: Optional[SubjectFilters],
) -> bool:
    """Return True if *day* has at least one visible lesson after all filtering."""
    _f = filters or {}
    for lesson in day.lessons:
        body = _render_lesson_body(lesson, user_subgroup, display_mode, _f)
        if body is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# "No lessons" block helper
# ---------------------------------------------------------------------------

def fmt_no_lessons(
    next_day: Optional[DaySchedule],
    user_subgroup: Optional[str],
    display_mode: str,
    filters: Optional[SubjectFilters],
) -> str:
    text = "<i>Пар нет.</i>"
    if next_day:
        text += (
            f"\n\n<b>Следующие занятия — {fmt_date_header(next_day.date)}:</b>\n\n"
            + fmt_day(next_day, user_subgroup, display_mode, filters)
        )
    return text


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
        return f"{icon} {_snap_line(ch.new_lesson)}\n  {old_t} → {t}"
    return f"{icon} {_snap_line(ch.new_lesson or ch.old_lesson)}"


def _split_changes_by_subgroup(
    changes: list[ScheduleChange], user_subgroup: Optional[str]
) -> tuple[list[ScheduleChange], list[ScheduleChange]]:
    if not user_subgroup:
        return changes, []
    mine, other = [], []
    for ch in changes:
        snap = ch.new_lesson or ch.old_lesson
        sg = snap.subgroup if snap else None
        (mine if (sg is None or sg == user_subgroup) else other).append(ch)
    return mine, other


def _build_change_message(ch_list: list[ScheduleChange], title: str) -> str:
    by_date: dict[date, list[ScheduleChange]] = {}
    for c in ch_list:
        by_date.setdefault(c.lesson_date, []).append(c)
    parts = [f"<b>{title}</b>"]
    for d in sorted(by_date):
        parts.append(f"\n<b>{fmt_date_header(d)}</b>")
        for ch in by_date[d]:
            parts.append(_fmt_one_change(ch))
    return "\n".join(parts)


def fmt_changes(
    changes: list[ScheduleChange],
    user_subgroup: Optional[str] = None,
    diff_display_mode: str = "hide",
) -> tuple[str, Optional[str]]:
    """Returns (main_message, optional_second_message)."""
    if not changes:
        return "<i>Изменений нет.</i>", None

    mine, other = _split_changes_by_subgroup(changes, user_subgroup)
    main_parts: list[str] = []
    if mine:
        main_parts.append(_build_change_message(mine, "📣 Изменения в расписании"))

    second_msg: Optional[str] = None
    if other and diff_display_mode != "hide":
        if diff_display_mode == "separate":
            second_msg = _build_change_message(other, "📣 Изменения (другая подгруппа)")
        else:
            other_lines = ["\n<i>Другая подгруппа:</i>"]
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
    "hide":                  "🙈 Скрыть",
    "strikethrough":         "~~Зачеркнуть~~",
    "spoiler":               "👁 Спойлер",
    "spoiler_strikethrough": "👁+~~ Спойлер+зачерк.",
}

DIFF_DISPLAY_MODE_LABELS = {
    "hide":                  "🙈 Не показывать",
    "inline_strikethrough":  "~~В сообщении (зачерк.)~~",
    "inline_spoiler":        "👁 В сообщении (спойлер)",
    "separate":              "📨 Отдельным сообщением",
}

FILTER_TYPE_LABELS = {
    "always_show": "📌 Всегда показывать",
    "never_show":  "🚫 Всегда скрывать",
}
