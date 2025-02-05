import json
import os
import hashlib
import requests
from datetime import datetime, timedelta
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from PyPDF2 import PdfReader

# Настройки
BASE_URL = "https://www.vyatsu.ru/reports/schedule/Group/"
BASE_SES_URL = "https://www.vyatsu.ru/reports/schedule/Ses/"
FILE_STORAGE_PATH = "./downloaded_files/"
HASH_STORAGE_PATH = "./hashes/"
REQUIRED_KEYS = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "GROUP_ID", "ADMIN_ID"]
OPTIONAL_KEYS = ["SES1", "SES2"]
SECRETS_FILENAME = "secrets.json"

# Глобальная переменная для хранения даты последней проверки
last_check_time = None


def load_secrets():
    if os.path.exists(SECRETS_FILENAME):
        with open(SECRETS_FILENAME, 'r') as secrets_file:
            secrets = json.load(secrets_file)
            for key in REQUIRED_KEYS:
                if key not in secrets or not secrets[key]:
                    print(f"Missing or empty value for key: {key}.")
                    print("Please fill out secrets.json completely.")
                    exit(1)
    else:
        with open(SECRETS_FILENAME, 'w') as secrets_file:
            secrets_file.write(json.dumps(
                {key: "" if key != "ADMIN_ID" else ["", ""] for key in REQUIRED_KEYS + OPTIONAL_KEYS},
                separators=(',', ':')))
            print("The secrets.json file has been created. Please fill it in.")
            exit(1)
    return secrets


def calculate_session_date():
    if datetime.now().month == 1:
        session_num = "SES1"
    else:
        session_num = "SES2"
    if secrets[session_num] == "":
        return [datetime.now(), datetime.now()]
    return [datetime(day=int(secrets[session_num].split("_")[0][0:2]),
                     month=int(secrets[session_num].split("_")[0][2:4]),
                     year=int(secrets[session_num].split("_")[0][4:8]),
                     ),
            datetime(day=int(secrets[session_num].split("_")[1][0:2]),
                     month=int(secrets[session_num].split("_")[1][2:4]),
                     year=int(secrets[session_num].split("_")[1][4:8]),
                     ),
            ]


# Функция для расчета двухнедельных интервалов
def calculate_schedule_ranges(current_date=None):
    if current_date is None:
        current_date = datetime.now()
    if current_date.month == 1 or current_date.month == 6 or current_date.month == 7:
        # Время сессии
        session_date = calculate_session_date()
        if session_date[0] < current_date < session_date[1]:
            return [session_date]
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
    bot = Bot(token=secrets['TELEGRAM_TOKEN'])
    try:
        with open(file_path, "rb") as f:
            await bot.send_document(chat_id=secrets['TELEGRAM_CHAT_ID'], document=f,
                                    caption=str(calculate_hash(file_path)))
        if difference_text:
            await bot.send_message(
                chat_id=secrets['TELEGRAM_CHAT_ID'],
                text=f"Изменения в расписании:\n\n{difference_text}",
                parse_mode=ParseMode.HTML,
            )
        print(f"Файл {file_path} и изменения успешно отправлены в Telegram.")
    except TelegramError as e:
        print(f"Ошибка отправки в Telegram: {e}")


# Основная функция проверки расписания
async def check_schedule(debug=False):
    global last_check_time
    today = datetime.now()
    date_ranges = calculate_schedule_ranges(today)

    for start_date, end_date in date_ranges:
        if 9 <= start_date.month <= 12 or len(date_ranges) == 1 and start_date.month == 1:
            semester = '1'
        else:
            semester = '2'
        url = f"{BASE_URL if len(date_ranges) == 2 else BASE_SES_URL}{secrets['GROUP_ID']}_{semester}_{format_date(start_date)}_{format_date(end_date)}.pdf"
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
                    if debug == True:
                        bot = Bot(token=secrets['TELEGRAM_TOKEN'])
                        await bot.send_message(
                            chat_id=secrets['TELEGRAM_CHAT_ID'],
                            text=f"Файл {file_name} не изменился.",
                        )
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
            if debug == True:
                bot = Bot(token=secrets['TELEGRAM_TOKEN'])
                await bot.send_message(
                    chat_id=secrets['TELEGRAM_CHAT_ID'],
                    text=f"Не удалось скачать файл по ссылке: {url}",
                )

    # Обновляем время последней проверки
    last_check_time = datetime.now()


# Проверка, является ли пользователь администратором
def is_admin(user_id):
    return str(user_id) in secrets["ADMIN_ID"]


# Обработчик команды /ping
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return  # Не отвечаем, если пользователь не администратор
    global last_check_time
    if last_check_time:
        last_check_str = last_check_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        last_check_str = "Проверка еще не выполнялась."
    await update.message.reply_text(f"Pong! Бот активен.\nПоследняя проверка расписания: {last_check_str}")


# Обработчик команды /update
async def update_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return  # Не отвечаем, если пользователь не администратор
    await update.message.reply_text("Запуск проверки расписания...")
    await check_schedule(True)
    await update.message.reply_text("Проверка расписания завершена.")


# Основной цикл приложения
async def main():
    os.makedirs(FILE_STORAGE_PATH, exist_ok=True)
    os.makedirs(HASH_STORAGE_PATH, exist_ok=True)
    global secrets
    secrets = load_secrets()

    # Создаем приложение и добавляем обработчики команд
    application = Application.builder().token(secrets['TELEGRAM_TOKEN']).build()
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("update", update_schedule))

    # Запускаем приложение
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    while True:
        print(f"[{datetime.now()}] Запуск проверки расписания...")
        await check_schedule()
        print(f"[{datetime.now()}] Проверка завершена. Следующая проверка через 1 час.")
        await asyncio.sleep(3600)  # Пауза на 1 час


# Запуск приложения
if __name__ == "__main__":
    asyncio.run(main())
