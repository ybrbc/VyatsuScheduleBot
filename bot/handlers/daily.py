"""Daily notification job.

Runs every minute. For users whose daily_time matches HH:MM now:
  - Sends today's OR tomorrow's schedule (based on daily_send_tomorrow).
  - Logs the send in DailyNotificationLog for resend tracking.

Resend logic (triggered from notification_service after a schedule change):
  - If a user received a daily notification today for target_date X,
    and lessons on date X have since changed, resend the updated schedule.
  - Cooldown: 30 minutes between resends per user per target_date.
  - Header changes based on whether target_date is today or in the future.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.connection import get_session
from database.models import User
from repositories import user_repository as ur
from repositories import daily_log_repository as dlr
from services import schedule_service as ss
from utils.formatter import fmt_days, fmt_date_header, SubjectFilters

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schedule_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


async def _build_schedule_text(
    user: User,
    target_date: date,
    filters: SubjectFilters,
) -> tuple[str, str]:
    """Return (header, body) for the schedule on target_date."""
    today = date.today()
    label = "завтра" if target_date > today else "сегодня"
    header = (
        f"☀️ Расписание на <b>{label}</b>, "
        f"{fmt_date_header(target_date)}"
    )

    days = await asyncio.to_thread(ss.get_today, user.group_id, target_date)
    dm = user.display_mode or "hide"
    sg = user.subgroup

    if not days:
        body = "<i>Пар нет.</i>"
    else:
        body = fmt_days(days, user_subgroup=sg, display_mode=dm, filters=filters)

    return header, body


# ---------------------------------------------------------------------------
# Job: send initial daily notifications
# ---------------------------------------------------------------------------

async def send_daily_schedules(bot: Bot) -> None:
    """Called every minute. Sends daily schedule to users whose time matches now."""
    now = datetime.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    current_hm = (now.hour, now.minute)

    with get_session() as session:
        users = ur.get_daily_users(session)

    to_notify = [
        u for u in users
        if u.daily_time
        and (u.daily_time.hour, u.daily_time.minute) == current_hm
        # and u.last_daily_sent != today
    ]

    if not to_notify:
        return

    logger.info("Sending daily notifications to %d user(s)", len(to_notify))

    for user in to_notify:
        target_date = tomorrow if user.daily_send_tomorrow else today

        def _get_filters(tg_id=user.telegram_id):
            with get_session() as s:
                return ur.get_filters_dict(s, tg_id)

        filters = await asyncio.to_thread(_get_filters)

        try:
            header, body = await _build_schedule_text(user, target_date, filters)
            await bot.send_message(
                chat_id=user.telegram_id,
                text=f"<b>{header}</b>\n\n{body}",
                parse_mode=ParseMode.HTML,
            )

            # Log the send and mark today as sent
            def _persist(uid=user.id, td=target_date, sent=now, tg=user.telegram_id):
                with get_session() as s:
                    dlr.upsert_log(s, uid, td, today, sent)
                    ur.update_last_daily_sent(s, tg, today)

            await asyncio.to_thread(_persist)

        except TelegramError as exc:
            logger.warning("Daily notify failed for %s: %s", user.telegram_id, exc)
        except Exception as exc:
            logger.exception("Unexpected error for %s: %s", user.telegram_id, exc)


# ---------------------------------------------------------------------------
# Resend updated schedule after a change is detected
# ---------------------------------------------------------------------------

async def resend_for_changed_dates(
    bot: Bot,
    group_id: int,
    changed_dates: set[date],
) -> None:
    """Called by notification_service after schedule changes are detected.

    For each changed date, find users who already received a daily notification
    today for that date and resend the updated schedule (with cooldown).
    """
    today = date.today()

    for target_date in changed_dates:
        with get_session() as session:
            logs = dlr.get_logs_for_target(session, target_date, today)

        for log in logs:
            # Check the user belongs to this group and cooldown has passed
            with get_session() as session:
                user = session.query(User).filter_by(id=log.user_id).first()
                if user is None or user.group_id != group_id:
                    continue
                if not dlr.can_resend(log):
                    logger.debug(
                        "Cooldown active for user %s target %s", user.telegram_id, target_date
                    )
                    continue

            def _get_filters(tg_id=user.telegram_id):
                with get_session() as s:
                    return ur.get_filters_dict(s, tg_id)

            filters = await asyncio.to_thread(_get_filters)

            # Determine label depending on when the change was detected
            if target_date > today:
                change_label = "на <b>завтра</b>"
            else:
                change_label = "на <b>сегодня</b>"

            try:
                _, body = await _build_schedule_text(user, target_date, filters)
                text = (
                    f"⚠️ Расписание {change_label} изменилось!\n"
                    f"Актуальное расписание — {fmt_date_header(target_date)}:\n\n"
                    f"{body}"
                )
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                logger.info(
                    "Resent updated schedule to %s for %s", user.telegram_id, target_date
                )

                # Update resent timestamp
                def _mark(log_id=log.id):
                    with get_session() as s:
                        dlr.mark_resent(s, log_id)

                await asyncio.to_thread(_mark)

            except TelegramError as exc:
                logger.warning(
                    "Resend failed for %s: %s", user.telegram_id, exc
                )
