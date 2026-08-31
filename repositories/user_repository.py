"""User repository."""
from __future__ import annotations
import logging
from datetime import date, time
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from database.models import User

logger = logging.getLogger(__name__)


def get_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    return session.query(User).filter_by(telegram_id=telegram_id).first()


def get_or_create(session: Session, telegram_id: int) -> tuple[User, bool]:
    user = get_by_telegram_id(session, telegram_id)
    if user:
        return user, False
    user = User(telegram_id=telegram_id)
    session.add(user)
    session.flush()
    return user, True


def set_group(session: Session, telegram_id: int, group_id: int) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.group_id = group_id
    user.subgroup = None
    session.flush()
    return user


def set_subgroup(session: Session, telegram_id: int, subgroup: Optional[str]) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.subgroup = subgroup
    session.flush()
    return user


def set_display_mode(session: Session, telegram_id: int, mode: str) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.display_mode = mode
    session.flush()
    return user


def set_diff_display_mode(session: Session, telegram_id: int, mode: str) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.diff_display_mode = mode
    session.flush()
    return user


def set_change_notifications(session: Session, telegram_id: int, enabled: bool) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.change_notifications = enabled
    session.flush()
    return user


def set_daily_time(
    session: Session, telegram_id: int, t: Optional[time], enabled: bool = True
) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.daily_time = t
    user.daily_notifications = enabled and t is not None
    session.flush()
    return user


def update_last_daily_sent(session: Session, telegram_id: int, sent_date: date) -> None:
    user = get_by_telegram_id(session, telegram_id)
    if user:
        user.last_daily_sent = sent_date
        session.flush()


def get_subscribed_users(session: Session, group_id: int) -> list[User]:
    return (
        session.query(User)
        .filter_by(group_id=group_id, change_notifications=True)
        .options(joinedload(User.group))
        .all()
    )


def get_daily_users(session: Session) -> list[User]:
    """All users with daily notifications enabled."""
    return (
        session.query(User)
        .filter(
            User.daily_notifications.is_(True),
            User.daily_time.isnot(None),
            User.group_id.isnot(None),
        )
        .options(joinedload(User.group))
        .all()
    )
