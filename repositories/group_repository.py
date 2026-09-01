"""Group repository — manage Group records in the database."""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Group

logger = logging.getLogger(__name__)


def get_all(session: Session) -> list[Group]:
    return session.query(Group).all()


def get_active(session: Session) -> list[Group]:
    return session.query(Group).filter(Group.is_active.is_(True)).all()


def get_by_external_id(session: Session, external_id: str) -> Optional[Group]:
    return session.query(Group).filter(Group.external_id == external_id).first()


def get_by_id(session: Session, group_id: int) -> Optional[Group]:
    return session.query(Group).filter(Group.id == group_id).first()


def upsert_from_config(session: Session, groups_config: list[dict]) -> list[Group]:
    """Sync groups from config list into the DB. Creates missing, updates active flag."""
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
