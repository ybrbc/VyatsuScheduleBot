import os
import requests
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from config import SECRETS

from services.parser import extract_text_from_pdf, load_schedule_from_json
from services.diff import get_diff
from utils.formatter import format_output

BASE_URL = "https://www.vyatsu.ru/reports/schedule/Group/"
BASE_SES_URL = "https://www.vyatsu.ru/reports/schedule/Ses/"
FILE_STORAGE_PATH = "./storage/downloaded_files/"
FILE_PARSED_PATH = "./storage/parsed/"

last_check_time = None


def download_file(url, save_path):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(response.content)
        return True
    return False


async def send_to_telegram(file_path, difference_text=None):
    bot = Bot(token=SECRETS['TELEGRAM_TOKEN'])
    try:
        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=SECRETS['TELEGRAM_CHAT_ID'],
                document=f,
            )
        if difference_text:
            await bot.send_message(
                chat_id=SECRETS['TELEGRAM_CHAT_ID'],
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

    if not SECRETS.get(session_num):
        now = datetime.now()
        return now, now

    dates = SECRETS[session_num].split("_")
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


async def check_schedule(context : ContextTypes.DEFAULT_TYPE, debug=False):
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

        semester = await get_semester(date_ranges, start_date)
        url = await get_url(date_ranges, end_date, semester, start_date)
        file_name = await get_filename(end_date, start_date)
        file_path = os.path.join(FILE_STORAGE_PATH, file_name)

        if download_file(url, file_path):
            prev_file_path = f"{FILE_PARSED_PATH}previous.json"
            if os.path.exists(prev_file_path):
                os.remove(prev_file_path)
            os.rename(f"{FILE_PARSED_PATH}current.json", prev_file_path)
            new_text = extract_text_from_pdf(file_path, "current.json")

            if os.path.exists(prev_file_path):
                old_text = load_schedule_from_json("previous.json")
                if old_text and new_text:
                    difference = get_diff(old_text, new_text)

            if not difference:
                print(f"Файл {file_name} не изменился.")
                if debug:
                    bot = Bot(token=SECRETS['TELEGRAM_TOKEN'])
                    await bot.send_message(chat_id=SECRETS['TELEGRAM_CHAT_ID'],
                                           text=f"Файл {file_name} не изменился.")
                continue

            old_text_path = os.path.join(FILE_STORAGE_PATH, f"previous_{file_name}")
            await send_to_telegram(old_text_path, format_output(difference))

        else:
            print(f"Не удалось скачать файл по ссылке: {url}")
            if debug:
                bot = Bot(token=SECRETS['TELEGRAM_TOKEN'])
                await bot.send_message(chat_id=SECRETS['TELEGRAM_CHAT_ID'],
                                       text=f"Не удалось скачать файл по ссылке: {url}")

    last_check_time = datetime.now()
    context.bot_data["last_check_time"] = datetime.now()
    print("Следующая проверка расписания через 1 час")


async def get_filename(end_date, start_date):
    file_name = f"{format_date(start_date)}_{format_date(end_date)}.pdf"
    return file_name


async def get_url(date_ranges, end_date, semester, start_date):
    url = f"{BASE_URL if len(date_ranges) == 2 else BASE_SES_URL}{SECRETS['GROUP_ID']}_{semester}_{format_date(start_date)}_{format_date(end_date)}.pdf"
    return url


async def get_semester(date_ranges, start_date):
    semester = '1' if (9 <= start_date.month <= 12) or (len(date_ranges) == 1 and start_date.month == 1) else '2'
    return semester