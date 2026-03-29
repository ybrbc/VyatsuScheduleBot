from telegram import Update
from telegram.ext import ContextTypes
from services import scheduler
from utils.user_utils import is_admin
def is_admin(user_id, secrets):
    return str(user_id) in secrets["ADMIN_ID"]


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, scheduler.secrets):
        return
    last_check = context.bot_data.get("last_check_time")
    if last_check:
        last_check_str = last_check.strftime("%Y-%m-%d %H:%M:%S")
    else:
        last_check_str = "Проверка еще не выполнялась."
    await update.message.reply_text(f"Pong! Бот активен.\nПоследняя проверка расписания: {last_check_str}")


async def update_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, scheduler.secrets):
        return
    await update.message.reply_text("Запуск проверки расписания...")
    await scheduler.check_schedule(context.application)
    await update.message.reply_text("Проверка завершена.")
