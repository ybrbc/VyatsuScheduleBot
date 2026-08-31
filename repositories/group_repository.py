"""Group repository."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Group

logger = logging.getLogger(__name__)

# Daytime (6-21): check every 120 min. Night: every 60 min.
DAY_INTERVAL_SEC = 7200
NIGHT_INTERVAL_SEC = 3600


def _target_interval(now: Optional[datetime] = None) -> int:
    h = (now or datetime.now()).hour
    return DAY_INTERVAL_SEC if 6 <= h < 21 else NIGHT_INTERVAL_SEC


def get_all(session: Session) -> list[Group]:
    return session.query(Group).all()


def get_active(session: Session) -> list[Group]:
    return session.query(Group).filter(Group.is_active.is_(True)).all()


def get_by_external_id(session: Session, external_id: str) -> Optional[Group]:
    return session.query(Group).filter(Group.external_id == external_id).first()


def get_by_id(session: Session, group_id: int) -> Optional[Group]:
    return session.query(Group).filter(Group.id == group_id).first()


def get_next_due(session: Session) -> Optional[Group]:
    """Return the active group most overdue for a schedule check, or None."""
    now = datetime.now()
    interval = _target_interval(now)
    groups = get_active(session)
    if not groups:
        return None

    best: Optional[Group] = None
    best_overdue: float = 0.0

    for g in groups:
        if g.last_check_at is None:
            overdue = float("inf")
        else:
            elapsed = (now - g.last_check_at).total_seconds()
            overdue = elapsed - interval

        if overdue >= 0 and overdue > best_overdue:
            best_overdue = overdue
            best = g

    return best


def update_last_check(session: Session, group_id: int) -> None:
    g = session.query(Group).filter(Group.id == group_id).first()
    if g:
        g.last_check_at = datetime.now()
        session.flush()


def upsert_from_config(session: Session, groups_config: list[dict]) -> list[Group]:
    result: list[Group] = []
    for cfg in groups_config:
        ext_id = str(cfg["id"])
        name = cfg.get("name", ext_id)
        active = bool(cfg.get("active", True))

        grp = get_by_external_id(session, ext_id)
        if grp is None:
            grp = Group(external_id=ext_id, name=name, is_active=active)
            session.add(grp)
            logger.info("Created group %s (%s)", ext_id, name)
        else:
            grp.name = name
            grp.is_active = active
        result.append(grp)

    session.flush()
    return result
