import json
import os
import hashlib
import requests
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
import asyncio
from PyPDF2 import PdfReader

# Настройки
BASE_URL = "https://www.vyatsu.ru/reports/schedule/Group/"
FILE_STORAGE_PATH = "./downloaded_files/"
HASH_STORAGE_PATH = "./hashes/"
try:
    with open('secrets.json', 'r') as secrets_file:
        secrets = json.load(secrets_file)
except FileNotFoundError:
    with open('secrets.json', 'w') as secrets_file:
        secrets_file.write(json.dumps(
            {'TELEGRAM_TOKEN': "", 'TELEGRAM_CHAT_ID': '', "GROUP_ID": ""},
            separators=(',', ':')))
        print("Please edit secrets.json.")
        exit(0)
# Создаем необходимые папки, если их нет
os.makedirs(FILE_STORAGE_PATH, exist_ok=True)
os.makedirs(HASH_STORAGE_PATH, exist_ok=True)


# Функция для расчета двухнедельных интервалов
def calculate_schedule_ranges(current_date=None):
    if current_date is None:
        current_date = datetime.now()

    # Базовая дата начала расписания
    base_date = datetime(2024, 9, 2)

    # Вычисляем количество недель между текущей датой и базовой датой
    delta_weeks = (current_date - base_date).days // 7

    # Если количество недель не кратно 2, добавляем одну неделю
    if delta_weeks % 2 != 0:
        delta_weeks -= 1

    # Определяем начало текущего двухнедельного интервала
    interval_start = base_date + timedelta(weeks=delta_weeks)

    # Создаем интервалы
    current_range_start = interval_start
    current_range_end = interval_start + timedelta(days=13)
    next_range_start = current_range_start + timedelta(days=14)
    next_range_end = next_range_start + timedelta(days=13)

    return [
        (current_range_start, current_range_end),  # Текущий двухнедельный интервал
        (next_range_start, next_range_end),  # Следующий двухнедельный интервал
    ]


# Форматируем дату для ссылки
def format_date(date):
    return date.strftime("%d%m%Y")


# Скачивание файла
def download_file(url, save_path):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(response.content)
        return True
    return False


# Хэширование файла
def calculate_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# Извлечение текста из PDF
def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        print(f"Ошибка при извлечении текста из {file_path}: {e}")
        return None


# Отправка файла и текста в Telegram
async def send_to_telegram(file_path, difference_text=None):
    bot = Bot(token=secrets.TELEGRAM_TOKEN)
    try:
        with open(file_path, "rb") as f:
            await bot.send_document(chat_id=secrets.TELEGRAM_CHAT_ID, document=f, caption=str(calculate_hash(file_path)))
        if difference_text:
            await bot.send_message(
                chat_id=secrets.TELEGRAM_CHAT_ID,
                text=f"Изменения в расписании:\n\n{difference_text}",
                parse_mode=ParseMode.HTML,
            )
        print(f"Файл {file_path} и изменения успешно отправлены в Telegram.")
    except TelegramError as e:
        print(f"Ошибка отправки в Telegram: {e}")


# Основная функция проверки расписания
async def check_schedule():
    today = datetime.now()
    date_ranges = calculate_schedule_ranges(today)

    for start_date, end_date in date_ranges:
        url = f"{BASE_URL}_{secrets.GROUP_ID}_{'1' if today.month > 7 else '2'}_{format_date(start_date)}_{format_date(end_date)}.pdf"
        file_name = f"{format_date(start_date)}_{format_date(end_date)}.pdf"
        file_path = os.path.join(FILE_STORAGE_PATH, file_name)

        # Скачиваем файл
        if download_file(url, file_path):
            new_hash = calculate_hash(file_path)
            hash_file_path = os.path.join(HASH_STORAGE_PATH, f"{file_name}.hash")

            # Проверяем, изменился ли файл
            if os.path.exists(hash_file_path):
                with open(hash_file_path, "r") as f:
                    old_hash = f.read()
                if old_hash == new_hash:
                    print(f"Файл {file_name} не изменился.")
                    continue

            # Сохраняем новый хэш
            with open(hash_file_path, "w") as f:
                f.write(new_hash)

            # Сравниваем содержимое текста
            new_text = extract_text_from_pdf(file_path)
            old_text_path = os.path.join(FILE_STORAGE_PATH, f"previous_{file_name}")
            difference_text = None

            if os.path.exists(old_text_path):
                old_text = extract_text_from_pdf(old_text_path)
                if old_text and new_text:
                    old_lines = set(old_text.splitlines())
                    new_lines = set(new_text.splitlines())
                    difference = new_lines - old_lines
                    difference_text = "\n".join(difference)

            # Обновляем старый файл
            try:
                os.rename(file_path, old_text_path)
            except FileExistsError:
                os.remove(old_text_path)
                os.rename(file_path, old_text_path)
            # Отправляем файл и изменения
            await send_to_telegram(old_text_path, difference_text)
        else:
            print(f"Не удалось скачать файл по ссылке: {url}")


# Основной цикл приложения
async def main():
    while True:
        print(f"[{datetime.now()}] Запуск проверки расписания...")
        await check_schedule()
        print(f"[{datetime.now()}] Проверка завершена. Следующая проверка через 1 час.")
        await asyncio.sleep(3600)  # Пауза на 1 час


# Запуск приложения
if __name__ == "__main__":
    asyncio.run(main())
