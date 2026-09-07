"""Handlers for cumulative subject progress."""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.connection import get_session
from repositories import user_repository as ur
from services import progress_service as ps
from utils.formatter import fmt_progress


async def _load_progress(tg_id: int):
    def _load_user():
        with get_session() as session:
            user = ur.get_by_telegram_id(session, tg_id)
            if not user or not user.group_id:
                return None, None
            return user.group_id, user.subgroup

    group_id, subgroup = await asyncio.to_thread(_load_user)
    if not group_id:
        return None

    return await asyncio.to_thread(ps.get_progress, group_id, subgroup)


async def handle_progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    items = await _load_progress(update.effective_user.id)
    if items is None:
        await update.message.reply_text(
            "⚠️ Группа не выбрана. Используйте /start."
        )
        return

    await update.message.reply_text(
        fmt_progress(items),
        parse_mode=ParseMode.HTML,
    )


async def cb_progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    items = await _load_progress(update.effective_user.id)
    if items is None:
        await query.answer("Сначала выберите группу в /start", show_alert=True)
        return

    await query.message.reply_text(
        fmt_progress(items),
        parse_mode=ParseMode.HTML,
    )
