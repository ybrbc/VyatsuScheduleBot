"""Notification service: broadcast schedule changes to Telegram users."""
from __future__ import annotations
import logging
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
    *,
    user_subgroup: str | None = None,
) -> int:
    """Send change notifications to all subscribed users of *group_id*.

    Returns the number of successfully notified users.
    """
    if not changes:
        return 0

    with get_session() as session:
        users = ur.get_subscribed_users(session, group_id)

    if not users:
        return 0

    message = fmt_changes(changes)
    notified = 0

    for user in users:
        # Apply per-user subgroup filter if needed
        user_sg = user_subgroup or user.subgroup
        visible = _filter_for_user(changes, user_sg)
        if not visible:
            continue

        text = fmt_changes(visible)
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            notified += 1
        except TelegramError as exc:
            logger.warning("Failed to notify user %s: %s", user.telegram_id, exc)

    logger.info("Notified %d/%d users for group_id=%s", notified, len(users), group_id)
    return notified


def _filter_for_user(
    changes: list[ScheduleChange], subgroup: str | None
) -> list[ScheduleChange]:
    """Keep only changes relevant to the user's subgroup (None = all)."""
    if not subgroup:
        return changes

    relevant: list[ScheduleChange] = []
    for ch in changes:
        snap = ch.new_lesson or ch.old_lesson
        if snap is None or snap.subgroup is None or snap.subgroup == subgroup:
            relevant.append(ch)
    return relevant
