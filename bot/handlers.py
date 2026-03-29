from telegram import Update
from telegram.ext import ContextTypes
from services import scheduler
from utils.user_utils import is_admin


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    last_check = context.bot_data.get("last_check_time")
    if last_check:
        last_check_str = last_check.strftime("%Y-%m-%d %H:%M:%S")
    else:
        last_check_str = "Проверка еще не выполнялась."
    await update.message.reply_text(f"Pong! Бот активен.\nПоследняя проверка расписания: {last_check_str}")


async def update_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return

    if context.bot_data.get("is_updating") == True:
        await update.message.reply_text("Бот уже выполняет обновление.")
        return

    try:
        context.bot_data["is_updating"] = True
        await update.message.reply_text("Запуск проверки расписания...")
        await scheduler.check_schedule(context)
        await update.message.reply_text("Проверка завершена.")
    finally:
        context.bot_data["is_updating"] = False
