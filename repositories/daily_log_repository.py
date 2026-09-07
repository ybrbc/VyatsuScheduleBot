"""Daily notification log repository.

Tracks which schedule date was sent to each user and when,
so we can resend an updated schedule if the target date's lessons change.

Resend cooldown: 30 minutes between resends per user per target_date.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DailyNotificationLog

logger = logging.getLogger(__name__)

RESEND_COOLDOWN = timedelta(minutes=30)


def upsert_log(
    session: Session,
    user_id: int,
    target_date: date,
    notification_date: date,
    sent_at: datetime,
) -> DailyNotificationLog:
    """Create or refresh the log entry for a user × target_date on this calendar day."""
    row = (
        session.query(DailyNotificationLog)
        .filter_by(user_id=user_id, target_date=target_date,
                   notification_date=notification_date)
        .first()
    )
    if row is None:
        row = DailyNotificationLog(
            user_id=user_id,
            target_date=target_date,
            notification_date=notification_date,
            sent_at=sent_at,
        )
        session.add(row)
    else:
        row.sent_at = sent_at
        row.last_resent_at = None   # reset on fresh daily send
    session.flush()
    return row


def get_logs_for_target(
    session: Session,
    target_date: date,
    notification_date: date,
) -> list[DailyNotificationLog]:
    """Return all users who received a daily notification today for target_date."""
    return (
        session.query(DailyNotificationLog)
        .filter_by(target_date=target_date, notification_date=notification_date)
        .all()
    )


def can_resend(log: DailyNotificationLog) -> bool:
    """True if enough time has passed since the last resend (or first send)."""
    ref = log.last_resent_at or log.sent_at
    return (datetime.now() - ref) >= RESEND_COOLDOWN


def mark_resent(session: Session, log_id: int) -> None:
    row = session.query(DailyNotificationLog).filter_by(id=log_id).first()
    if row:
        row.last_resent_at = datetime.now()
        session.flush()
