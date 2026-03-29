from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

class TelegramClient:
    def __init__(self, token):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.bot = Bot(token=token, request=request)

    async def send_file(self, chat_id, file_path, caption):
        try:
            with open(file_path, "rb") as f:
                await self.bot.send_document(chat_id=chat_id, document=f, caption=caption)
        except TelegramError as e:
            print(f"Telegram error: {e}")

    async def send_message(self, chat_id, text):
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except TelegramError as e:
            print(f"Telegram error: {e}")