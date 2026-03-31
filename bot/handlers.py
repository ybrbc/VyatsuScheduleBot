import os
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from services import scheduler
from services.parser import extract_text_from_pdf
from services.scheduler import calculate_schedule_ranges, get_filename, FILE_STORAGE_PATH
from utils.user_utils import is_admin, send_long_message


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


async def print_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return

    date_ranges = calculate_schedule_ranges(datetime.now())[0]

    start_date, end_date = date_ranges[0], date_ranges[1]
    file_name = await get_filename(end_date, start_date)
    file_path = os.path.join(FILE_STORAGE_PATH, file_name)

    text = extract_text_from_pdf(file_path)
    await send_long_message(context.bot, update.message.from_user.id,  text, ParseMode.MARKDOWN_V2, "```json\n")
    return
