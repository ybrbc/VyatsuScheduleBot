"""Subject filter settings: always_show / never_show per-subject-id.

Each Subject DB row uniquely identifies (title + lesson_type + teacher + subgroup),
so users can independently hide/show e.g.:
  "Элективные / Практика / пд.01 / Полубоярцев"  ← keep
  "Элективные / Практика / пд.01 / Крестьянинова" ← hide

Callback pattern: "sf:{action}:{args...}"
  sf:list:{filter_type}               → show list of active filters
  sf:add:{filter_type}:{page}         → paginated subject selector
  sf:set:{filter_type}:{subject_id}   → add/update filter, return to list
  sf:del:{filter_id}:{filter_type}    → delete filter, return to list
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.connection import get_session
from database.models import UserSubjectFilter
from models.domain import SubjectInfo
from repositories import user_repository as ur
from repositories import schedule_repository as sr
from utils.formatter import FILTER_TYPE_LABELS

logger = logging.getLogger(__name__)

PAGE_SIZE = 6   # subjects per page in the add-screen


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def _list_kb(
    filters: list[UserSubjectFilter],
    subjects_by_id: dict[int, SubjectInfo],
    filter_type: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for f in filters:
        info = subjects_by_id.get(f.subject_id)
        label = info.short_label(28) if info else f"subject #{f.subject_id}"
        rows.append([
            InlineKeyboardButton(f"📋 {label}", callback_data="noop"),
            InlineKeyboardButton("🗑", callback_data=f"sf:del:{f.id}:{filter_type}"),
        ])
    rows.append([InlineKeyboardButton("➕ Добавить", callback_data=f"sf:add:{filter_type}:0")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(rows)


def _add_kb(
    all_subjects: list[SubjectInfo],
    active_ids: set[int],
    filter_type: str,
    page: int,
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(all_subjects) + PAGE_SIZE - 1) // PAGE_SIZE)
    slice_start = page * PAGE_SIZE
    page_subjects = all_subjects[slice_start: slice_start + PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for info in page_subjects:
        # Show a checkmark when this subject is already in the filter
        tick = "✅ " if info.id in active_ids else ""
        label = tick + info.short_label(30)
        rows.append([
            InlineKeyboardButton(label, callback_data=f"sf:set:{filter_type}:{info.id}")
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Пред", callback_data=f"sf:add:{filter_type}:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("След →", callback_data=f"sf:add:{filter_type}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Назад", callback_data=f"sf:list:{filter_type}")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_group_id(tg_id: int) -> Optional[int]:
    def _q():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            return user.group_id if user else None
    return await asyncio.to_thread(_q)


async def _load_subjects(group_id: int) -> list[SubjectInfo]:
    def _q():
        with get_session() as s:
            return sr.get_subjects_for_group(s, group_id)
    return await asyncio.to_thread(_q)


async def _load_filters(tg_id: int, filter_type: str):
    def _q():
        with get_session() as s:
            all_f = ur.get_subject_filters(s, tg_id)
            return [f for f in all_f if f.filter_type == filter_type]
    return await asyncio.to_thread(_q)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

async def cb_subject_filter(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id

    parts = query.data.split(":", 3)
    action = parts[1] if len(parts) > 1 else ""
    p2     = parts[2] if len(parts) > 2 else ""
    p3     = parts[3] if len(parts) > 3 else ""

    if action == "list":
        await _show_list(query, tg_id, p2)

    elif action == "add":
        page = int(p3) if p3.isdigit() else 0
        await _show_add(query, tg_id, filter_type=p2, page=page)

    elif action == "set":
        subject_id = int(p3) if p3.lstrip("-").isdigit() else None
        if subject_id is None:
            return
        await _toggle_filter(query, tg_id, filter_type=p2, subject_id=subject_id)

    elif action == "del":
        fid = int(p2) if p2.isdigit() else 0
        await _del_filter(query, tg_id, filter_id=fid, filter_type=p3)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

async def _show_list(query, tg_id: int, filter_type: str) -> None:
    filters = await _load_filters(tg_id, filter_type)

    # Build a map subject_id → SubjectInfo for display
    subject_ids = {f.subject_id for f in filters}
    subjects_map: dict[int, SubjectInfo] = {}
    if subject_ids:
        group_id = await _load_group_id(tg_id)
        if group_id:
            all_subjects = await _load_subjects(group_id)
            subjects_map = {s.id: s for s in all_subjects}

    label = FILTER_TYPE_LABELS.get(filter_type, filter_type)
    header = f"<b>{label}</b>"
    if filters:
        lines = []
        for f in filters:
            info = subjects_map.get(f.subject_id)
            lines.append("• " + (info.full_label() if info else f"subject #{f.subject_id}"))
        header += "\n\n" + "\n".join(lines)
    else:
        header += "\n\n<i>Список пуст.</i>"

    await query.edit_message_text(
        header, parse_mode=ParseMode.HTML,
        reply_markup=_list_kb(filters, subjects_map, filter_type),
    )


async def _show_add(query, tg_id: int, filter_type: str, page: int) -> None:
    group_id = await _load_group_id(tg_id)
    if not group_id:
        await query.answer("Группа не выбрана", show_alert=True)
        return

    all_subjects = await _load_subjects(group_id)
    if not all_subjects:
        await query.answer("Расписание ещё не загружено", show_alert=True)
        return

    # Collect IDs already in THIS filter type
    filters = await _load_filters(tg_id, filter_type)
    active_ids = {f.subject_id for f in filters}

    label = FILTER_TYPE_LABELS.get(filter_type, filter_type)
    total_pages = max(1, (len(all_subjects) + PAGE_SIZE - 1) // PAGE_SIZE)
    await query.edit_message_text(
        f"<b>{label}</b>\n\n"
        f"Выберите предмет (стр. {page+1}/{total_pages}, всего {len(all_subjects)}):",
        parse_mode=ParseMode.HTML,
        reply_markup=_add_kb(all_subjects, active_ids, filter_type, page),
    )


async def _toggle_filter(
    query, tg_id: int, filter_type: str, subject_id: int
) -> None:
    """Add filter if absent; remove if already set to same type."""
    def _save():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            if not user:
                return "no_user"
            existing = (
                s.query(UserSubjectFilter)
                .filter_by(user_id=user.id, subject_id=subject_id)
                .first()
            )
            if existing and existing.filter_type == filter_type:
                # Toggle off — remove
                s.delete(existing)
                s.flush()
                return "removed"
            elif existing:
                # Change type
                existing.filter_type = filter_type
                s.flush()
                return "changed"
            else:
                s.add(UserSubjectFilter(
                    user_id=user.id, subject_id=subject_id, filter_type=filter_type
                ))
                s.flush()
                return "added"

    result = await asyncio.to_thread(_save)
    tips = {"removed": "🗑 Убрано", "changed": "✏️ Обновлено", "added": "✅ Добавлено"}
    await query.answer(tips.get(result, "OK"))

    # Refresh the add-screen so checkmarks update
    group_id = await _load_group_id(tg_id)
    if group_id:
        all_subjects = await _load_subjects(group_id)
        filters = await _load_filters(tg_id, filter_type)
        active_ids = {f.subject_id for f in filters}
        # Find current page
        idx = next((i for i, s in enumerate(all_subjects) if s.id == subject_id), 0)
        page = idx // PAGE_SIZE
        label = FILTER_TYPE_LABELS.get(filter_type, filter_type)
        total_pages = max(1, (len(all_subjects) + PAGE_SIZE - 1) // PAGE_SIZE)
        await query.edit_message_text(
            f"<b>{label}</b>\n\n"
            f"Выберите предмет (стр. {page+1}/{total_pages}, всего {len(all_subjects)}):",
            parse_mode=ParseMode.HTML,
            reply_markup=_add_kb(all_subjects, active_ids, filter_type, page),
        )


async def _del_filter(
    query, tg_id: int, filter_id: int, filter_type: str
) -> None:
    def _del():
        with get_session() as s:
            return ur.delete_subject_filter(s, filter_id, tg_id)
    deleted = await asyncio.to_thread(_del)
    if deleted:
        await query.answer("🗑 Удалено")
    await _show_list(query, tg_id, filter_type)
