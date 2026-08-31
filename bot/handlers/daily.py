"""Daily notification job: send today's schedule at the user's chosen time."""
from __future__ import annotations
import asyncio
import logging
from datetime import date, datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.connection import get_session
from repositories import user_repository as ur
from services import schedule_service as ss
from utils.formatter import fmt_days, fmt_date_header

logger = logging.getLogger(__name__)


async def send_daily_schedules(bot: Bot) -> None:
    """Called every minute by the job queue.

    Finds users whose daily_time matches the current HH:MM and
    sends their schedule if not already sent today.
    """
    now = datetime.now()
    today = now.date()
    current_hm = (now.hour, now.minute)

    with get_session() as session:
        users = ur.get_daily_users(session)

    to_notify = [
        u for u in users
        if u.daily_time
        and (u.daily_time.hour, u.daily_time.minute) == current_hm
        and u.last_daily_sent != today
    ]

    if not to_notify:
        return

    logger.info("Sending daily schedule to %d user(s)", len(to_notify))

    for user in to_notify:
        try:
            days = await asyncio.to_thread(ss.get_today, user.group_id)
            header = f"✉️ Расписание на {fmt_date_header(today)}"

            if days:
                text = (
                    f"<b>{header}</b>\n\n"
                    + fmt_days(
                        days,
                        user_subgroup=user.subgroup,
                        display_mode=user.display_mode or "hide",
                    )
                )

                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )

            # Mark as sent for today
            def _mark():
                with get_session() as s:
                    ur.update_last_daily_sent(s, user.telegram_id, today)

            await asyncio.to_thread(_mark)

        except TelegramError as exc:
            logger.warning("Daily notify failed for %s: %s", user.telegram_id, exc)
        except Exception as exc:
            logger.exception("Unexpected error in daily notify for %s: %s",
                             user.telegram_id, exc)
