"""Notification service: send change alerts + trigger daily resends."""
from __future__ import annotations
import logging
from datetime import date
from typing import TYPE_CHECKING

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.connection import get_session
from models.domain import ScheduleChange
from repositories import user_repository as ur
from utils.formatter import fmt_changes

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def notify_group_users(
    bot: Bot,
    group_id: int,
    changes: list[ScheduleChange],
) -> int:
    """Send personalised change diff notifications to subscribed users.

    Also triggers a resend of the daily schedule for users who already
    received a daily notification for any of the changed dates.

    Returns the number of successfully notified users.
    """
    if not changes:
        return 0

    with get_session() as session:
        users = ur.get_subscribed_users(session, group_id)

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

    # Resend updated daily schedule to users whose daily notification
    # was already sent today for one of the changed dates.
    changed_dates: set[date] = {ch.lesson_date for ch in changes}
    if changed_dates:
        from bot.handlers.daily import resend_for_changed_dates
        await resend_for_changed_dates(bot, group_id, changed_dates)

    return notified
