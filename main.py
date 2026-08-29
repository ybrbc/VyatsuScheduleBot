"""Vyatsu Schedule Bot — main entry point.

Initialises:
  - logging
  - database (creates tables)
  - groups from secrets.json
  - Telegram Application with handlers
  - hourly update job
"""
from __future__ import annotations
import asyncio
import logging
import os
import sys
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import SECRETS
from database.connection import init_db
from database.connection import get_session
from repositories import group_repository as gr
from bot.handlers.admin import cmd_ping, cmd_update
from bot.handlers.schedule import (
    cmd_start,
    cb_group_selected,
    handle_today,
    handle_tomorrow,
    handle_week,
    handle_two_weeks,
)
from bot.handlers.settings import handle_settings, cb_settings, cb_subgroup_selected
from services import schedule_updater as su
from utils.user_utils import configure as configure_admin_ids

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(__file__), "storage", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
    ],
)
# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("camelot").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _init_app() -> None:
    """Initialise DB and sync groups from config."""
    db_url = SECRETS["DATABASE_URL"]
    init_db(db_url)

    groups_cfg = SECRETS.get("GROUPS", [])
    if groups_cfg:
        with get_session() as session:
            gr.upsert_from_config(session, groups_cfg)
        logger.info("Groups synced: %s", [g["id"] for g in groups_cfg])
    else:
        logger.warning("No GROUPS defined in secrets.json — add at least one group.")

    configure_admin_ids(SECRETS.get("ADMIN_IDS", []))


# ---------------------------------------------------------------------------
# Periodic job
# ---------------------------------------------------------------------------

async def _hourly_update_job(ctx) -> None:
    """Called by the job queue every hour."""
    logger.info("Hourly schedule check started")
    stats = await su.run_update(bot=ctx.bot)
    logger.info("Hourly check done: %s", stats.summary())


# ---------------------------------------------------------------------------
# Application build
# ---------------------------------------------------------------------------

def build_app() -> Application:
    token = SECRETS["TELEGRAM_TOKEN"]
    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("update", cmd_update))

    # Main menu text buttons
    app.add_handler(MessageHandler(filters.Regex("^📅 Сегодня$"), handle_today))
    app.add_handler(MessageHandler(filters.Regex("^➡️ Завтра$"), handle_tomorrow))
    app.add_handler(MessageHandler(filters.Regex("^🗓 Неделя$"), handle_week))
    app.add_handler(MessageHandler(filters.Regex("^📖 2 недели$"), handle_two_weeks))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Настройки$"), handle_settings))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(cb_group_selected, pattern=r"^grp:"))
    app.add_handler(CallbackQueryHandler(cb_subgroup_selected, pattern=r"^sg:"))
    app.add_handler(CallbackQueryHandler(cb_settings, pattern=r"^settings:"))

    # Hourly job — start after 60 s to let the bot warm up
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(_hourly_update_job, interval=3600, first=60)
        logger.info("Hourly update job scheduled")

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== Vyatsu Schedule Bot starting ===")
    try:
        _init_app()
    except Exception as exc:
        logger.critical("Startup failed: %s", exc)
        sys.exit(1)

    app = build_app()
    logger.info("Bot polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
