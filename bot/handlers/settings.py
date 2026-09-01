"""Settings handlers."""
from __future__ import annotations
import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.keyboards.main import settings_menu, subgroup_selection, group_selection
from database.connection import get_session
from repositories import group_repository as gr
from repositories import user_repository as ur

logger = logging.getLogger(__name__)


async def handle_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id

    def _load():
        with get_session() as s:
            user, _ = ur.get_or_create(s, tg_id)
            return user.change_notifications, user.subgroup, user.group_id

    change_notif, subgroup, group_id = await asyncio.to_thread(_load)

    if not group_id:
        await update.message.reply_text(
            "⚠️ Сначала выберите группу через /start."
        )
        return

    await update.message.reply_text(
        "⚙️ <b>Настройки</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=settings_menu(change_notif, subgroup),
    )


async def cb_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    tg_id = update.effective_user.id

    if action == "subgroup":
        await query.edit_message_text(
            "👤 Выберите подгруппу:",
            reply_markup=subgroup_selection(),
        )

    elif action == "toggle_notif":
        def _toggle():
            with get_session() as s:
                user, _ = ur.get_or_create(s, tg_id)
                new_val = not user.change_notifications
                ur.set_change_notifications(s, tg_id, new_val)
                return new_val, user.subgroup

        new_val, subgroup = await asyncio.to_thread(_toggle)
        label = "🔔 включены" if new_val else "🔕 выключены"
        await query.edit_message_text(
            f"⚙️ <b>Настройки</b>\n\nУведомления об изменениях: {label}",
            parse_mode=ParseMode.HTML,
            reply_markup=settings_menu(new_val, subgroup),
        )

    elif action == "change_group":
        def _groups():
            with get_session() as s:
                return gr.get_active(s)

        groups = await asyncio.to_thread(_groups)
        await query.edit_message_text(
            "🔄 Выберите новую группу:",
            reply_markup=group_selection(groups),
        )


async def cb_subgroup_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    sg = query.data.split(":", 1)[1]  # "01", "02", or "all"
    tg_id = update.effective_user.id

    actual_sg = None if sg == "all" else sg

    def _save():
        with get_session() as s:
            ur.set_subgroup(s, tg_id, actual_sg)

    await asyncio.to_thread(_save)
    label = f"подгруппа {actual_sg}" if actual_sg else "обе подгруппы"
    await query.edit_message_text(f"✅ Выбрана {label}.")
