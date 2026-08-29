"""User repository."""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from database.models import Group, User

logger = logging.getLogger(__name__)


def get_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    return session.query(User).filter_by(telegram_id=telegram_id).first()


def get_or_create(session: Session, telegram_id: int) -> tuple[User, bool]:
    """Return (user, created). *created* is True for new users."""
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
    user.subgroup = None  # reset subgroup on group change
    session.flush()
    return user


def set_subgroup(session: Session, telegram_id: int, subgroup: Optional[str]) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.subgroup = subgroup
    session.flush()
    return user


def set_change_notifications(
    session: Session, telegram_id: int, enabled: bool
) -> User:
    user, _ = get_or_create(session, telegram_id)
    user.change_notifications = enabled
    session.flush()
    return user


def get_subscribed_users(session: Session, group_id: int) -> list[User]:
    """Users subscribed to change notifications for a specific group."""
    return (
        session.query(User)
        .filter_by(group_id=group_id, change_notifications=True)
        .options(joinedload(User.group))
        .all()
    )


def get_all_users(session: Session) -> list[User]:
    return session.query(User).options(joinedload(User.group)).all()
