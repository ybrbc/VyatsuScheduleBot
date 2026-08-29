"""Admin handlers: /ping and /update."""
from __future__ import annotations
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services import schedule_updater as su
from utils.user_utils import is_admin, notify_admin

logger = logging.getLogger(__name__)


async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    last = su.last_update_time()
    last_str = last.strftime("%d.%m.%Y %H:%M:%S") if last else "никогда"
    status = "🔄 Выполняется" if su.is_running() else "✅ Готов"

    await update.message.reply_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"Статус: {status}\n"
        f"Последняя проверка: {last_str}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return

    if su.is_running():
        await update.message.reply_text("⏳ Обновление уже выполняется. Подождите.")
        return

    await update.message.reply_text("🔄 Запуск обновления расписания…")

    bot = ctx.bot
    stats = await su.run_update(bot=bot)

    await update.message.reply_text(stats.summary(), parse_mode=ParseMode.HTML)
