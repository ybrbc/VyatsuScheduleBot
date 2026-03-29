# services/scheduler.py
import os
import hashlib
import requests
from datetime import datetime, timedelta
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from services.parser import extract_text_from_pdf, Day  # Day + PDF-парсер

# Настройки путей и URL
BASE_URL = "https://www.vyatsu.ru/reports/schedule/Group/"
BASE_SES_URL = "https://www.vyatsu.ru/reports/schedule/Ses/"
FILE_STORAGE_PATH = "./storage/downloaded_files/"
HASH_STORAGE_PATH = "./storage/hashes/"

last_check_time = None
secrets = None  # Подставляется из main.py


# --- Скачивание файлов ---
def download_file(url, save_path):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(response.content)
        return True
    return False


# --- Хэширование файла ---
def calculate_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# --- Отправка в Telegram ---
async def send_to_telegram(file_path, difference_text=None):
    bot = Bot(token=secrets['TELEGRAM_TOKEN'])
    try:
        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=secrets['TELEGRAM_CHAT_ID'],
                document=f,
                caption=str(calculate_hash(file_path))
            )
        if difference_text:
            await bot.send_message(
                chat_id=secrets['TELEGRAM_CHAT_ID'],
                text=f"Изменения в расписании:\n\n{difference_text}",
                parse_mode=ParseMode.HTML,
            )
        print(f"Файл {file_path} и изменения успешно отправлены в Telegram.")
    except TelegramError as e:
        print(f"Ошибка отправки в Telegram: {e}")


# --- Сессия ---
def calculate_session_date():
    if datetime.now().month == 1:
        session_num = "SES1"
    else:
        session_num = "SES2"

    if not secrets.get(session_num):
        now = datetime.now()
        return now, now

    dates = secrets[session_num].split("_")
    start_str, end_str = dates[0], dates[1]

    session_start = datetime(
        day=int(start_str[0:2]),
        month=int(start_str[2:4]),
        year=int(start_str[4:8])
    )
    session_end = datetime(
        day=int(end_str[0:2]),
        month=int(end_str[2:4]),
        year=int(end_str[4:8])
    )
    return session_start, session_end


# --- Двухнедельные интервалы ---
def calculate_schedule_ranges(current_date=None):
    if current_date is None:
        current_date = datetime.now()

    if current_date.month in (1, 6, 7):
        session_start, session_end = calculate_session_date()
        if session_start <= current_date <= session_end:
            return [(session_start, session_end)]

    base_date = datetime(2024, 9, 2)
    delta_weeks = (current_date - base_date).days // 7
    if delta_weeks % 2 != 0:
        delta_weeks -= 1
    interval_start = base_date + timedelta(weeks=delta_weeks)

    current_range_start = interval_start
    current_range_end = interval_start + timedelta(days=13)
    next_range_start = current_range_start + timedelta(days=14)
    next_range_end = next_range_start + timedelta(days=13)

    return [
        (current_range_start, current_range_end),
        (next_range_start, next_range_end)
    ]


def format_date(date):
    return date.strftime("%d%m%Y")


# --- Основная проверка расписания ---
async def check_schedule(app, debug=False):
    global last_check_time
    today = datetime.now()

    date_ranges = calculate_schedule_ranges(today)
    if not date_ranges:
        print("Не удалось вычислить диапазоны дат для расписания.")
        return

    for interval in date_ranges:
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            start_date, end_date = interval
        else:
            start_date, end_date = interval[0], interval[1]

        semester = '1' if (9 <= start_date.month <= 12) or (len(date_ranges) == 1 and start_date.month == 1) else '2'
        url = f"{BASE_URL if len(date_ranges) == 2 else BASE_SES_URL}{secrets['GROUP_ID']}_{semester}_{format_date(start_date)}_{format_date(end_date)}.pdf"
        file_name = f"{format_date(start_date)}_{format_date(end_date)}.pdf"
        file_path = os.path.join(FILE_STORAGE_PATH, file_name)

        if download_file(url, file_path):
            new_hash = calculate_hash(file_path)
            hash_file_path = os.path.join(HASH_STORAGE_PATH, f"{file_name}.hash")

            if os.path.exists(hash_file_path):
                with open(hash_file_path, "r") as f:
                    old_hash = f.read()
                if old_hash == new_hash:
                    print(f"Файл {file_name} не изменился.")
                    if debug:
                        bot = Bot(token=secrets['TELEGRAM_TOKEN'])
                        await bot.send_message(chat_id=secrets['TELEGRAM_CHAT_ID'],
                                               text=f"Файл {file_name} не изменился.")
                    continue

            with open(hash_file_path, "w") as f:
                f.write(new_hash)

            new_text = extract_text_from_pdf(file_path)
            old_text_path = os.path.join(FILE_STORAGE_PATH, f"previous_{file_name}")
            difference_text = None

            if os.path.exists(old_text_path):
                old_text = extract_text_from_pdf(old_text_path)
                if old_text and new_text:
                    old_lines = set(old_text.splitlines())
                    new_lines = set(new_text.splitlines())
                    difference_text = "\n".join(new_lines - old_lines)

            try:
                os.rename(file_path, old_text_path)
            except FileExistsError:
                os.remove(old_text_path)
                os.rename(file_path, old_text_path)

            await send_to_telegram(old_text_path, difference_text)

        else:
            print(f"Не удалось скачать файл по ссылке: {url}")
            if debug:
                bot = Bot(token=secrets['TELEGRAM_TOKEN'])
                await bot.send_message(chat_id=secrets['TELEGRAM_CHAT_ID'],
                                       text=f"Не удалось скачать файл по ссылке: {url}")

    last_check_time = datetime.now()
    app.bot_data["last_check_time"] = datetime.now()
    print("Следующая проверка расписания через 1 час")