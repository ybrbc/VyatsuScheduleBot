"""Schedule handlers: /start, and the main menu buttons."""
from __future__ import annotations
import asyncio
import logging
from datetime import date

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.keyboards.main import group_selection, main_menu
from database.connection import get_session
from repositories import group_repository as gr
from repositories import user_repository as ur
from services import schedule_service as ss
from models.domain import DaySchedule
from utils.formatter import fmt_days, fmt_date_header
from utils.user_utils import send_long_message

logger = logging.getLogger(__name__)

_MONTHS_RU = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id

    # Check if user already has a group
    def _load():
        with get_session() as s:
            user, created = ur.get_or_create(s, tg_id)
            group = user.group
            return user.group_id, group.name if group else None, created

    group_id, group_name, created = await asyncio.to_thread(_load)

    if group_id and not created:
        await update.message.reply_text(
            f"👋 Привет! Ваша группа: <b>{group_name}</b>.\n\n"
            f"Используйте кнопки меню ниже.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    # Show group selection
    def _groups():
        with get_session() as s:
            return gr.get_active(s)

    groups = await asyncio.to_thread(_groups)
    if not groups:
        await update.message.reply_text(
            "⚠️ Нет активных групп. Обратитесь к администратору."
        )
        return

    await update.message.reply_text(
        "👋 Добро пожаловать в <b>Vyatsu Schedule Bot</b>!\n\n"
        "Выберите вашу группу:",
        parse_mode=ParseMode.HTML,
        reply_markup=group_selection(groups),
    )


# ---------------------------------------------------------------------------
# Callback: group selected
# ---------------------------------------------------------------------------

async def cb_group_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ext_id = query.data.split(":", 1)[1]
    tg_id = update.effective_user.id

    def _save():
        with get_session() as s:
            group = gr.get_by_external_id(s, ext_id)
            if group is None:
                return None
            ur.set_group(s, tg_id, group.id)
            return group.name or group.external_id

    group_name = await asyncio.to_thread(_save)
    if group_name is None:
        await query.edit_message_text("⚠️ Группа не найдена.")
        return

    await query.edit_message_text(
        f"✅ Группа <b>{group_name}</b> выбрана!\n\nИспользуйте кнопки меню.",
        parse_mode=ParseMode.HTML,
    )
    await ctx.bot.send_message(
        chat_id=tg_id,
        text="Главное меню:",
        reply_markup=main_menu(),
    )


# ---------------------------------------------------------------------------
# Schedule views
# ---------------------------------------------------------------------------

async def _get_user_group(tg_id: int):
    """Return (group_id, subgroup) or (None, None) if not configured."""
    def _q():
        with get_session() as s:
            user = ur.get_by_telegram_id(s, tg_id)
            if user is None or user.group_id is None:
                return None, None
            return user.group_id, user.subgroup
    return await asyncio.to_thread(_q)


async def _send_schedule(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    days: list[DaySchedule],
    header: str,
    user_subgroup: str | None,
) -> None:
    if not days:
        await update.message.reply_text(
            f"{header}\n\n<i>Расписание не найдено для этого периода.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    text = f"<b>{header}</b>" + fmt_days(days, user_subgroup=user_subgroup)
    await send_long_message(ctx.bot, update.effective_chat.id, text)


async def handle_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, subgroup = await _get_user_group(update.effective_user.id)
    if not group_id:
        await update.message.reply_text(
            "⚠️ Группа не выбрана. Используйте /start для настройки."
        )
        return

    today = date.today()
    header = f"📅 Сегодня, {fmt_date_header(today)}"
    days = await asyncio.to_thread(ss.get_today, group_id)
    await _send_schedule(update, ctx, days, header, subgroup)


async def handle_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, subgroup = await _get_user_group(update.effective_user.id)
    if not group_id:
        await update.message.reply_text("⚠️ Группа не выбрана. Используйте /start.")
        return

    from datetime import timedelta
    tomorrow = date.today() + timedelta(days=1)
    header = f"➡️ Завтра, {fmt_date_header(tomorrow)}"
    days = await asyncio.to_thread(ss.get_tomorrow, group_id)
    await _send_schedule(update, ctx, days, header, subgroup)


async def handle_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, subgroup = await _get_user_group(update.effective_user.id)
    if not group_id:
        await update.message.reply_text("⚠️ Группа не выбрана. Используйте /start.")
        return

    days = await asyncio.to_thread(ss.get_week, group_id)
    await _send_schedule(update, ctx, days, "🗓 Расписание на неделю", subgroup)


async def handle_two_weeks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    group_id, subgroup = await _get_user_group(update.effective_user.id)
    if not group_id:
        await update.message.reply_text("⚠️ Группа не выбрана. Используйте /start.")
        return

    days = await asyncio.to_thread(ss.get_two_weeks, group_id)
    await _send_schedule(update, ctx, days, "📖 Расписание на 2 недели", subgroup)
