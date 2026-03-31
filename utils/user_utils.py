from telegram import Bot
from telegram.constants import ParseMode

from config import SECRETS


def is_admin(user_id: int) -> bool:
    admin_list = SECRETS.get("ADMIN_ID", [])
    return str(user_id) in admin_list

async def send_long_message(bot: Bot, chat_id: int, text: str, parse_mode: ParseMode=ParseMode.HTML, md_format_start =""):

    md_format_end = ("" if len(md_format_start) == 0 else "```")
    md_format_len = len(md_format_start) + len(md_format_end)

    MAX_LENGTH = 4096 - md_format_len

    while len(text) > 0:
        if len(text) <= MAX_LENGTH:
            await bot.send_message(chat_id=chat_id, text=md_format_start +  text + md_format_end, parse_mode=parse_mode)
            break

        # Берем максимально допустимый кусок
        chunk = text[:MAX_LENGTH]

        # Ищем последний перенос строки в этом куске
        last_newline = chunk.rfind('\n')

        if last_newline != -1:
            # Если нашли \n, обрезаем по нему
            send_chunk = text[:last_newline + 1]
            text = text[last_newline + 1:]

        else:
            # Если \n нет, режем жестко по лимиту
            send_chunk = chunk
            text = text[MAX_LENGTH:]


        await bot.send_message(chat_id=chat_id, text=md_format_start + send_chunk + md_format_end, parse_mode=parse_mode)
