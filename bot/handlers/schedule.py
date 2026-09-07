"""Schedule handlers: /start, /today, /tomorrow, /week, /twoweeks and keyboard buttons."""
from __future__ import annotations
import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.keyboards.main import main_kb, start_hub_kb, group_selection_kb
from database.connection import get_session
from repositories import group_repository as gr
from repositories import user_repository as ur
from services import schedule_service as ss
from models.domain import DaySchedule
from utils.formatter import (
    fmt_days, fmt_day, fmt_date_header,
    fmt_no_lessons, has_visible_lessons, SubjectFilters,
)
from utils.user_utils import send_long_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    name = update.effective_user.first_name or "друг"

    def _load():
        with get_session() as s:
            user, _ = ur.get_or_create(s, tg_id)
            grp = user.group
            return user.group_id, (grp.name if grp else None)

    group_id, group_name = await asyncio.to_thread(_load)

    # Always refresh the bottom keyboard
    await update.message.reply_text(
        "Клавиатура обновлена.", reply_markup=main_kb()
    )

    if not group_id:
        def _groups():
            with get_session() as s:
                return gr.get_active(s)
        groups = await asyncio.to_thread(_groups)
        from telegram import InlineKeyboardMarkup
        raw_kb = group_selection_kb(groups, back_cb="start:hub")
        rows = [row for row in raw_kb.inline_keyboard
                if not any("Назад" in b.text for b in row)]
        await update.message.reply_text(
            f"👋 Привет, <b>{name}</b>!\n\nВыберите вашу учебную группу:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    await update.message.reply_text(
        f"👋 Привет, <b>{name}</b>!\n\n📚 Группа: <b>{group_name or group_id}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=start_hub_kb(True, group_name),
    )


# ---------------------------------------------------------------------------
# Callback: view from inline hub
# ---------------------------------------------------------------------------

async def cb_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    tg_id = update.effective_user.id

    group_id, sg, dm, filters = await _get_user_context(tg_id)
    if not group_id:
        await query.answer("Сначала выберите группу в /start", show_alert=True)
        return

    today = date.today()
    if action == "today":
        days = await asyncio.to_thread(ss.get_today, group_id)
        header = f"📅 Сегодня, {fmt_date_header(today)}"
        from_date = today
    elif action == "tomorrow":
        days = await asyncio.to_thread(ss.get_tomorrow, group_id)
        tomorrow = today + timedelta(days=1)
        header = f"➡️ Завтра, {fmt_date_header(tomorrow)}"
        from_date = tomorrow
    elif action == "week":
        days = await asyncio.to_thread(ss.get_week, group_id)
        header = "🗓 Расписание на неделю"
        from_date = today + timedelta(days=6 - today.weekday())  # next Sunday
    else:
        days = await asyncio.to_thread(ss.get_two_weeks, group_id)
        header = "📖 Расписание на 2 недели"
        from_date = None  # no "next" for 2-week view

    await _send_schedule(
        ctx.bot, query.message.chat_id, days, header,
        sg, dm, filters, group_id, from_date,
        view_type=action,
    )


# ---------------------------------------------------------------------------
# Callback: group selected
# ---------------------------------------------------------------------------

async def cb_group_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 2)
    ext_id = parts[1]
    back_cb = parts[2] if len(parts) > 2 else "start:hub"
    tg_id = update.effective_user.id

    def _save():
        with get_session() as s:
            group = gr.get_by_external_id(s, ext_id)
            if group is None:
                return None, None
            ur.set_group(s, tg_id, group.id)
            return group.id, group.name or group.external_id

    group_id, group_name = await asyncio.to_thread(_save)
    if group_id is None:
        await query.edit_message_text("⚠️ Группа не найдена.")
        return

    if back_cb == "start:hub":
        await query.edit_message_text(
            f"✅ Группа <b>{group_name}</b> выбрана!",
            parse_mode=ParseMode.HTML,
            reply_markup=start_hub_kb(True, group_name),
        )
    elif back_cb == "st:home":
        from bot.handlers.settings import _build_settings_msg
        text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Callback: back to /start hub
# ---------------------------------------------------------------------------

async def cb_start_hub(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tg_id = update.effective_user.id

    def _load():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            if user and user.group:
                return True, user.group.name or user.group.external_id
            return False, None

    has_group, name = await asyncio.to_thread(_load)
    await query.edit_message_text(
        f"📚 Группа: <b>{name}</b>" if has_group else "Группа не выбрана.",
        parse_mode=ParseMode.HTML,
        reply_markup=start_hub_kb(has_group, name),
    )


# ---------------------------------------------------------------------------
# User context helper
# ---------------------------------------------------------------------------

async def _get_user_context(tg_id: int) -> tuple[
    Optional[int], Optional[str], str, SubjectFilters
]:
    def _q():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            if not user or not user.group_id:
                return None, None, "hide", {}
            fdict = ur.get_filters_dict(s, tg_id)
            return user.group_id, user.subgroup, user.display_mode or "hide", fdict
    return await asyncio.to_thread(_q)


# ---------------------------------------------------------------------------
# Schedule reply helper (with "no lessons → next" fallback)
# ---------------------------------------------------------------------------

async def _send_schedule(
    bot, chat_id: int,
    days: list[DaySchedule],
    header: str,
    subgroup: Optional[str],
    display_mode: str,
    filters: SubjectFilters,
    group_id: int,
    from_date: Optional[date],
    view_type: str = "today",
) -> None:
    # Check visibility after filtering
    visible_days = [
        d for d in days
        if has_visible_lessons(d, subgroup, display_mode, filters)
    ]
    if not visible_days:
        # Find next day with visible lessons
        next_day: Optional[DaySchedule] = None
        if view_type != "two_weeks" and from_date is not None:
            next_day = await asyncio.to_thread(
                ss.get_next_lessons_day, group_id, from_date,
                subgroup, display_mode, filters,
            )

        text = f"<b>{header}</b>\n\n" + fmt_no_lessons(next_day, subgroup, display_mode, filters)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        return

    text = f"<b>{header}</b>\n\n" + fmt_days(visible_days, subgroup, display_mode, filters)
    await send_long_message(bot, chat_id, text)


# ---------------------------------------------------------------------------
# Bottom-keyboard handlers and /commands
# ---------------------------------------------------------------------------

async def _no_group(update: Update) -> None:
    await update.message.reply_text(
        "⚠️ Группа не выбрана. Используйте /start."
    )


async def handle_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm, f = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    today = date.today()
    days = await asyncio.to_thread(ss.get_today, group_id)
    await _send_schedule(
        ctx.bot, update.effective_chat.id, days,
        f"📅 Сегодня, {fmt_date_header(today)}",
        sg, dm, f, group_id, today, "today",
    )


async def handle_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm, f = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    tomorrow = date.today() + timedelta(days=1)
    days = await asyncio.to_thread(ss.get_tomorrow, group_id)
    await _send_schedule(
        ctx.bot, update.effective_chat.id, days,
        f"➡️ Завтра, {fmt_date_header(tomorrow)}",
        sg, dm, f, group_id, tomorrow, "tomorrow",
    )


async def handle_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm, f = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    today = date.today()
    end_of_week = today + timedelta(days=6 - today.weekday())
    days = await asyncio.to_thread(ss.get_week, group_id)
    await _send_schedule(
        ctx.bot, update.effective_chat.id, days,
        "🗓 Расписание на неделю",
        sg, dm, f, group_id, end_of_week, "week",
    )


async def handle_two_weeks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm, f = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    days = await asyncio.to_thread(ss.get_two_weeks, group_id)
    await _send_schedule(
        ctx.bot, update.effective_chat.id, days,
        "📖 Расписание на 2 недели",
        sg, dm, f, group_id, None, "two_weeks",
    )


async def handle_next_weeks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm, f = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    today = date.today()
    end_of_week = today + timedelta(days=6 + 7 - today.weekday())
    days = await asyncio.to_thread(ss.get_next_week, group_id)
    await _send_schedule(
        ctx.bot, update.effective_chat.id, days,
        "🗒 Расписание на следующую неделю",
        sg, dm, f, group_id, end_of_week, "week",
    )