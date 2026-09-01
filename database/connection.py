"""Database connection management.

Usage (sync):
    from database.connection import get_session
    with get_session() as session:
        ...  # session auto-commits on exit, rolls back on exception

Usage (async via thread):
    import asyncio
    result = await asyncio.to_thread(sync_function, args)
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def init_db(database_url: str) -> None:
    """Initialise engine, create all tables, configure session factory."""
    global _engine, _SessionFactory

    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False,
    )

    # For SQLite: enable WAL mode for concurrent access
    if database_url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(_engine)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    logger.info("Database initialised: %s", database_url.split("@")[-1])


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that yields a session, commits on success, rolls back on error."""
    if _SessionFactory is None:
        raise RuntimeError("DB not initialised — call init_db() first")
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if the DB is reachable."""
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("DB connection check failed: %s", exc)
        return False
