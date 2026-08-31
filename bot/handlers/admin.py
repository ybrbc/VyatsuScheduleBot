"""Admin handlers: /ping and /update."""
from __future__ import annotations
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services import schedule_updater as su
from utils.user_utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    last = su.last_update_time()
    last_str = last.strftime("%d.%m.%Y %H:%M:%S") if last else "никогда"
    running = su.is_running()

    await update.message.reply_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"Статус: {'🔄 Выполняется' if running else '✅ Готов'}\n"
        f"Последняя проверка: <b>{last_str}</b>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    if su.is_running():
        await update.message.reply_text("⏳ Обновление уже выполняется.")
        return

    msg = await update.message.reply_text("🔄 Запуск полного обновления…")
    stats = await su.run_update(bot=ctx.bot)
    await msg.edit_text(stats.summary(), parse_mode=ParseMode.HTML)
