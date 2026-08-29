"""Schedule updater: orchestrates the full update pipeline.

Pipeline per group × period:
  1. Build PDF URL
  2. Download (skip if HTTP 404)
  3. MD5 hash check (skip if unchanged)
  4. Parse PDF → Schedule domain object
  5. Validate schedule
  6. Load existing DaySchedule list from DB for diff
  7. BEGIN TRANSACTION → save new schedule + update hash → COMMIT
  8. Calculate diff between old and new lessons
  9. Send change notifications
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
    build_pdf_filename,
    get_biweekly_periods,
    get_semester,
    should_download,
)
from utils.hashing import file_md5
from utils.user_utils import notify_admin

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(__file__))
STORAGE_DIR = os.path.join(_ROOT, "storage", "downloaded_files")
BASE_URL: str = SECRETS.get("BASE_URL", "")
ADMIN_CHAT_ID: str = str(SECRETS.get("ADMIN_CHAT_ID", ""))

_update_lock = asyncio.Lock()
_is_updating: bool = False
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
            f"Пропущено (без изменений): <b>{self.skipped}</b>\n"
            f"Ошибок: <b>{self.errors}</b>"
        )


def last_update_time() -> Optional[datetime]:
    return _last_update


def is_running() -> bool:
    return _is_updating


async def run_update(bot: Optional[Bot] = None) -> UpdateStats:
    """Run a full update for all active groups. Concurrent calls are dropped."""
    global _is_updating, _last_update

    if _is_updating:
        logger.warning("Update already running — skipping concurrent call")
        return UpdateStats()

    async with _update_lock:
        _is_updating = True
        stats = UpdateStats()
        try:
            await _do_update(bot, stats)
        except Exception as exc:
            logger.exception("Unexpected error in run_update: %s", exc)
            stats.errors += 1
        finally:
            _last_update = datetime.now()
            _is_updating = False

    return stats


async def _do_update(bot: Optional[Bot], stats: UpdateStats) -> None:
    with get_session() as session:
        groups: list[Group] = gr.get_active(session)

    if not groups:
        logger.warning("No active groups — nothing to update")
        return

    periods = get_biweekly_periods(num=2)  # current + next biweekly window

    for group in groups:
        for p_start, p_end in periods:
            if not should_download(p_start, p_end):
                continue

            stats.checked += 1
            try:
                result = await _update_period(bot, group, p_start, p_end)
                if result is None:
                    stats.skipped += 1
                elif isinstance(result, list):
                    stats.changed += len(result)
            except Exception as exc:
                stats.errors += 1
                logger.exception(
                    "Error updating %s %s–%s: %s", group.external_id, p_start, p_end, exc
                )
                if bot and ADMIN_CHAT_ID:
                    await notify_admin(
                        bot, ADMIN_CHAT_ID,
                        f"⚠️ Ошибка обновления группы <b>{group.external_id}</b> "
                        f"({p_start}–{p_end}):\n<code>{exc}</code>",
                    )


async def _update_period(
    bot: Optional[Bot], group: Group, p_start, p_end
) -> Optional[list[ScheduleChange]]:
    """Process one period for one group.

    Returns:
      None            — skipped (no change or download failed)
      []              — first-time save (no diff to send)
      [changes...]    — changes detected and notifications sent
    """
    semester = get_semester(p_start)
    filename = build_pdf_filename(group.external_id, semester, p_start, p_end)
    url = BASE_URL + filename
    save_path = os.path.join(STORAGE_DIR, filename)
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # 1. Download
    downloaded = await asyncio.to_thread(download_pdf, url, save_path)
    if not downloaded:
        return None

    # 2. Hash check
    new_hash = await asyncio.to_thread(file_md5, save_path)
    with get_session() as session:
        old_hash = sr.get_hash(session, group.id, p_start, p_end)

    if old_hash == new_hash:
        logger.debug("Unchanged: %s", filename)
        return None

    logger.info("Changed hash for %s %s–%s, parsing…", group.external_id, p_start, p_end)

    # 3. Parse
    schedule = await asyncio.to_thread(parse_pdf, save_path, group.external_id, p_start, p_end)
    if schedule is None:
        _warn_admin(bot, group.external_id, p_start, p_end, "Не удалось распарсить PDF")
        return None

    # 4. Validate
    ok, reason = validate_schedule(schedule)
    if not ok:
        _warn_admin(
            bot, group.external_id, p_start, p_end,
            f"Подозрительное расписание: {reason}. БД не изменена."
        )
        return None

    # 5. Load existing for diff (before overwriting)
    def _load_old():
        with get_session() as s:
            return sr.get_period_as_domain_days(s, group.id, p_start, p_end)

    old_days = await asyncio.to_thread(_load_old)
    is_first_save = not bool(old_days)

    # 6. Atomic save
    def _save():
        with get_session() as s:
            sr.save_schedule(s, group.id, schedule)
            sr.upsert_hash(s, group.id, p_start, p_end, new_hash)

    await asyncio.to_thread(_save)
    logger.info(
        "Saved %s %s–%s: %d days, %d lessons",
        group.external_id, p_start, p_end, len(schedule.days), schedule.total_lessons,
    )

    # 7. First-time save — no diff
    if is_first_save:
        logger.info("First save for %s — skipping diff/notify", group.external_id)
        return []

    # 8. Diff
    old_tagged = tag_lessons_with_date(old_days)
    new_tagged = tag_lessons_with_date(schedule.days)
    changes = calculate_diff(old_tagged, new_tagged)

    # 9. Notify
    if changes and bot:
        await notify_group_users(bot, group.id, changes)

    return changes


def _warn_admin(bot, ext_id, p_start, p_end, reason: str) -> None:
    """Schedule a fire-and-forget admin notification (best-effort)."""
    if not bot or not ADMIN_CHAT_ID:
        return
    text = (
        f"⚠️ <b>{ext_id}</b> ({p_start}–{p_end})\n{reason}"
    )
    asyncio.create_task(notify_admin(bot, ADMIN_CHAT_ID, text))
