from __future__ import annotations
import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

_admin_ids: list[str] = []


def configure(admin_ids: list[str]) -> None:
    global _admin_ids
    _admin_ids = [str(x) for x in admin_ids]


def is_admin(user_id: int) -> bool:
    return str(user_id) in _admin_ids


async def send_long_message(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str = ParseMode.HTML,
    max_len: int = 4096,
) -> None:
    """Split and send a message that may exceed Telegram's 4096-char limit."""
    while text:
        chunk = text[:max_len]
        if len(text) > max_len:
            # Try to break at a newline
            cut = chunk.rfind("\n")
            if cut > 0:
                chunk = text[:cut]
        text = text[len(chunk):]
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)
        except TelegramError as e:
            logger.error("send_long_message error: %s", e)
            break


async def notify_admin(bot: Bot, admin_chat_id: str | int, text: str) -> None:
    """Send a plain-text message to the admin chat."""
    try:
        await bot.send_message(chat_id=int(admin_chat_id), text=text, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        logger.error("notify_admin error: %s", e)
