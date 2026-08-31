"""Notification service: send change alerts to subscribed users."""
from __future__ import annotations
import logging
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.connection import get_session
from models.domain import ScheduleChange
from repositories import user_repository as ur
from utils.formatter import fmt_changes

logger = logging.getLogger(__name__)


async def notify_group_users(
    bot: Bot,
    group_id: int,
    changes: list[ScheduleChange],
) -> int:
    """Send personalised change notifications to all subscribed users of *group_id*.
    Returns number of successfully notified users.
    """
    if not changes:
        return 0

    with get_session() as session:
        users = ur.get_subscribed_users(session, group_id)

    if not users:
        return 0

    notified = 0
    for user in users:
        main_msg, second_msg = fmt_changes(
            changes,
            user_subgroup=user.subgroup,
            diff_display_mode=user.diff_display_mode,
        )
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=main_msg,
                parse_mode=ParseMode.HTML,
            )
            if second_msg:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=second_msg,
                    parse_mode=ParseMode.HTML,
                )
            notified += 1
        except TelegramError as exc:
            logger.warning("Failed to notify user %s: %s", user.telegram_id, exc)

    logger.info("Notified %d/%d users for group_id=%s", notified, len(users), group_id)
    return notified
