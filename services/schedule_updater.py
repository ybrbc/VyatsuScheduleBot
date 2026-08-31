"""Schedule updater: staggered pipeline — one group per trigger.

Job runs every STAGGER_SECONDS. Each call picks the most-overdue
active group and processes it (download → parse → diff → save → notify).

Intervals:
  Daytime (06:00-21:00) — check each group every 120 min
  Nighttime             — check each group every 60 min

With 30 groups and a 2-minute stagger interval:
  Night: 30 × 2 min = 60 min per full cycle  ✓
  Day:   each group waits 120 min → one check every ~4 min on average ✓
"""
from __future__ import annotations
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from telegram import Bot

from config import SECRETS
from database.connection import get_session
from database.models import Group
from models.domain import ScheduleChange
from repositories import group_repository as gr
from repositories import schedule_repository as sr
from services.diff_service import calculate_diff, tag_lessons_with_date
from services.downloader import download_pdf
from services.notification_service import notify_group_users
from services.parser import parse_pdf, validate_schedule
from utils.date_utils import (
    build_pdf_filename, get_biweekly_periods,
    get_semester, should_download,
)
from utils.hashing import file_md5
from utils.user_utils import notify_admin

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(__file__))
STORAGE_DIR = os.path.join(_ROOT, "storage", "downloaded_files")
BASE_URL: str = SECRETS.get("BASE_URL", "")
ADMIN_CHAT_ID: str = str(SECRETS.get("ADMIN_CHAT_ID", ""))

_update_lock = asyncio.Lock()
_last_update: Optional[datetime] = None


@dataclass
class UpdateStats:
    checked: int = 0
    changed: int = 0
    errors: int = 0
    skipped: int = 0
    started_at: datetime = field(default_factory=datetime.now)

    def summary(self) -> str:
        elapsed = int((datetime.now() - self.started_at).total_seconds())
        return (
            f"✅ Обновление завершено за {elapsed}с\n\n"
            f"Проверено периодов: <b>{self.checked}</b>\n"
            f"Изменений найдено: <b>{self.changed}</b>\n"
            f"Пропущено: <b>{self.skipped}</b>\n"
            f"Ошибок: <b>{self.errors}</b>"
        )


def last_update_time() -> Optional[datetime]:
    return _last_update


def is_running() -> bool:
    return _update_lock.locked()


# ---------------------------------------------------------------------------
# Staggered single-group trigger (called by the recurring job)
# ---------------------------------------------------------------------------

async def run_next_group(bot: Optional[Bot] = None) -> Optional[UpdateStats]:
    """Pick the most-overdue active group and update it.

    Called every STAGGER_SECONDS by the job queue.
    Returns None if no group is due.
    """
    global _last_update

    async with _update_lock:
        with get_session() as session:
            group = gr.get_next_due(session)

        if group is None:
            return None

        stats = UpdateStats()
        try:
            await _update_group(bot, group, stats)
        except Exception as exc:
            stats.errors += 1
            logger.exception("Error updating %s: %s", group.external_id, exc)
            if bot and ADMIN_CHAT_ID:
                await notify_admin(
                    bot, ADMIN_CHAT_ID,
                    f"⚠️ Ошибка обновления <b>{group.external_id}</b>:\n<code>{exc}</code>",
                )
        finally:
            with get_session() as session:
                gr.update_last_check(session, group.id)
            _last_update = datetime.now()

    return stats


# ---------------------------------------------------------------------------
# Force-update all groups (for /update admin command)
# ---------------------------------------------------------------------------

async def run_update(bot: Optional[Bot] = None) -> UpdateStats:
    """Force-check all active groups immediately (used by /update command)."""
    global _last_update

    async with _update_lock:
        stats = UpdateStats()
        with get_session() as session:
            groups = gr.get_active(session)

        for group in groups:
            try:
                await _update_group(bot, group, stats)
            except Exception as exc:
                stats.errors += 1
                logger.exception("Error updating %s: %s", group.external_id, exc)
                if bot and ADMIN_CHAT_ID:
                    await notify_admin(
                        bot, ADMIN_CHAT_ID,
                        f"⚠️ <b>{group.external_id}</b>: <code>{exc}</code>",
                    )
            finally:
                with get_session() as session:
                    gr.update_last_check(session, group.id)

        _last_update = datetime.now()

    return stats


# ---------------------------------------------------------------------------
# Per-group update
# ---------------------------------------------------------------------------

async def _update_group(
    bot: Optional[Bot], group: Group, stats: UpdateStats
) -> None:
    periods = get_biweekly_periods(num=2)
    for p_start, p_end in periods:
        if not should_download(p_start, p_end):
            continue
        stats.checked += 1
        result = await _update_period(bot, group, p_start, p_end)
        if result is None:
            stats.skipped += 1
        elif isinstance(result, list):
            stats.changed += len(result)


async def _update_period(
    bot: Optional[Bot], group: Group, p_start, p_end
) -> Optional[list[ScheduleChange]]:
    semester = get_semester(p_start)
    filename = build_pdf_filename(group.external_id, semester, p_start, p_end)
    url = BASE_URL + filename
    save_path = os.path.join(STORAGE_DIR, filename)
    os.makedirs(STORAGE_DIR, exist_ok=True)

    downloaded = await asyncio.to_thread(download_pdf, url, save_path)
    if not downloaded:
        return None

    new_hash = await asyncio.to_thread(file_md5, save_path)
    with get_session() as session:
        old_hash = sr.get_hash(session, group.id, p_start, p_end)

    if old_hash == new_hash:
        return None

    logger.info("Hash changed: %s %s–%s", group.external_id, p_start, p_end)

    schedule = await asyncio.to_thread(
        parse_pdf, save_path, group.external_id, p_start, p_end
    )
    if schedule is None:
        _warn(bot, group.external_id, p_start, p_end, "Не удалось распарсить PDF")
        return None

    ok, reason = validate_schedule(schedule)
    if not ok:
        _warn(bot, group.external_id, p_start, p_end,
              f"Подозрительное расписание: {reason}. БД не изменена.")
        return None

    def _load_old():
        with get_session() as s:
            return sr.get_period_as_domain_days(s, group.id, p_start, p_end)

    old_days = await asyncio.to_thread(_load_old)
    is_first = not bool(old_days)

    def _save():
        with get_session() as s:
            sr.save_schedule(s, group.id, schedule)
            sr.upsert_hash(s, group.id, p_start, p_end, new_hash)

    await asyncio.to_thread(_save)

    if is_first:
        logger.info("First save for %s — no diff sent", group.external_id)
        return []

    changes = calculate_diff(
        tag_lessons_with_date(old_days),
        tag_lessons_with_date(schedule.days),
    )
    if changes and bot:
        await notify_group_users(bot, group.id, changes)

    return changes


def _warn(bot, ext_id, p_start, p_end, reason: str) -> None:
    if not bot or not ADMIN_CHAT_ID:
        return
    asyncio.create_task(
        notify_admin(
            bot, ADMIN_CHAT_ID,
            f"⚠️ <b>{ext_id}</b> ({p_start}–{p_end})\n{reason}",
        )
    )
