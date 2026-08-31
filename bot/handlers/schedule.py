"""Schedule handlers: /start, /today, /tomorrow, /week, /twoweeks and keyboard buttons."""
from __future__ import annotations
import asyncio
import logging
from datetime import date, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.keyboards.main import main_kb, start_hub_kb, group_selection_kb
from database.connection import get_session
from repositories import group_repository as gr
from repositories import user_repository as ur
from services import schedule_service as ss
from models.domain import DaySchedule
from utils.formatter import fmt_days, fmt_date_header
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
            user, created = ur.get_or_create(s, tg_id)
            grp = user.group
            return user.group_id, (grp.name if grp else None), created

    group_id, group_name, created = await asyncio.to_thread(_load)
    has_group = bool(group_id)

    # Always send/refresh the bottom keyboard first
    await update.message.reply_text(
        "Клавиатура активирована.",
        reply_markup=main_kb(),
    )

    if not has_group:
        def _groups():
            with get_session() as s:
                return gr.get_active(s)
        groups = await asyncio.to_thread(_groups)

        kb = group_selection_kb(groups, back_cb="start:hub")
        # Remove the back button when there's no group yet
        from telegram import InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([row for row in kb.inline_keyboard if "← Назад" not in row[0].text])

        await update.message.reply_text(
            f"👋 Привет, <b>{name}</b>!\n\n"
            f"Выберите вашу учебную группу:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # Group is set — show the hub
    await update.message.reply_text(
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"📚 Группа: <b>{group_name or group_id}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=start_hub_kb(True, group_name),
    )


# ---------------------------------------------------------------------------
# Callback: view schedule from inline hub
# ---------------------------------------------------------------------------

async def cb_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]  # today / tomorrow / week / two_weeks
    tg_id = update.effective_user.id

    group_id, subgroup, display_mode = await _get_user_context(tg_id)
    if not group_id:
        await query.answer("Сначала выберите группу в /start", show_alert=True)
        return

    if action == "today":
        days = await asyncio.to_thread(ss.get_today, group_id)
        header = f"📅 Сегодня, {fmt_date_header(date.today())}"
    elif action == "tomorrow":
        days = await asyncio.to_thread(ss.get_tomorrow, group_id)
        header = f"➡️ Завтра, {fmt_date_header(date.today() + timedelta(days=1))}"
    elif action == "week":
        days = await asyncio.to_thread(ss.get_week, group_id)
        header = "🗓 Расписание на неделю"
    else:  # two_weeks
        days = await asyncio.to_thread(ss.get_two_weeks, group_id)
        header = "📖 Расписание на 2 недели"

    await _reply_schedule(ctx.bot, query.message.chat_id, days, header, subgroup, display_mode)


# ---------------------------------------------------------------------------
# Callback: group selected (from /start or settings)
# ---------------------------------------------------------------------------

async def cb_group_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # data format: "grp:{ext_id}:{back_cb}"
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

    # Return to correct destination
    if back_cb == "start:hub":
        await query.edit_message_text(
            f"✅ Группа <b>{group_name}</b> выбрана!\n\n"
            f"📚 Используйте кнопки ниже или быструю панель.",
            parse_mode=ParseMode.HTML,
            reply_markup=start_hub_kb(True, group_name),
        )
    elif back_cb == "st:home":
        # Return to settings after group change
        from bot.handlers.settings import _build_settings_msg
        text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Callback: navigate back to /start hub
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
# Text-button and command handlers (bottom keyboard + /commands)
# ---------------------------------------------------------------------------

async def _get_user_context(tg_id: int):
    def _q():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            if user is None or user.group_id is None:
                return None, None, "hide"
            return user.group_id, user.subgroup, user.display_mode or "hide"
    return await asyncio.to_thread(_q)


async def _no_group(update: Update) -> None:
    await update.message.reply_text(
        "⚠️ Группа не выбрана. Используйте /start для настройки."
    )


async def _reply_schedule(bot, chat_id, days, header, subgroup, display_mode):
    if not days:
        await bot.send_message(
            chat_id=chat_id,
            text=f"<b>{header}</b>\n\n<i>Расписание не найдено.</i>",
            parse_mode=ParseMode.HTML,
        )
        return
    text = f"<b>{header}</b>\n\n" + fmt_days(days, user_subgroup=subgroup, display_mode=display_mode)
    await send_long_message(bot, chat_id, text)


async def handle_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    days = await asyncio.to_thread(ss.get_today, group_id)
    await _reply_schedule(
        ctx.bot, update.effective_chat.id, days,
        f"📅 Сегодня, {fmt_date_header(date.today())}", sg, dm,
    )


async def handle_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    days = await asyncio.to_thread(ss.get_tomorrow, group_id)
    await _reply_schedule(
        ctx.bot, update.effective_chat.id, days,
        f"➡️ Завтра, {fmt_date_header(date.today() + timedelta(days=1))}", sg, dm,
    )


async def handle_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    days = await asyncio.to_thread(ss.get_week, group_id)
    await _reply_schedule(ctx.bot, update.effective_chat.id, days, "🗓 Неделя", sg, dm)


async def handle_two_weeks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, sg, dm = await _get_user_context(update.effective_user.id)
    if not group_id:
        await _no_group(update); return
    days = await asyncio.to_thread(ss.get_two_weeks, group_id)
    await _reply_schedule(ctx.bot, update.effective_chat.id, days, "📖 2 недели", sg, dm)
