"""Vyatsu Schedule Bot — entry point.

Job schedule:
  Every 2 minutes  : stagger_job  — check the most-overdue group
  Every 1 minute   : daily_job    — send daily schedules at configured times
"""
from __future__ import annotations
import logging
import os
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import SECRETS
from database.connection import init_db, get_session
from repositories import group_repository as gr

# Handlers
from bot.handlers.admin import cmd_ping, cmd_update
from bot.handlers.schedule import (
    cmd_start, cb_group_selected, cb_view, cb_start_hub,
    handle_today, handle_tomorrow, handle_week, handle_two_weeks,
)
from bot.handlers.settings import (
    cmd_settings, cb_settings, handle_custom_time_input,
)
from bot.handlers.daily import send_daily_schedules

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
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("camelot").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# How often to trigger a single-group check (seconds)
STAGGER_INTERVAL = 120   # 2 minutes → 30 groups/hour at night, 15/hour daytime


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _init_app() -> None:
    init_db(SECRETS["DATABASE_URL"])

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

async def _stagger_job(ctx) -> None:
    """Process the most-overdue group."""
    await su.run_next_group(bot=ctx.bot)


async def _daily_job(ctx) -> None:
    """Send daily schedule notifications."""
    await send_daily_schedules(bot=ctx.bot)


# ---------------------------------------------------------------------------
# Application build
# ---------------------------------------------------------------------------

def build_app() -> Application:
    token = SECRETS["TELEGRAM_TOKEN"]
    app = Application.builder().token(token).build()

    # --- Commands ---
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", handle_today))
    app.add_handler(CommandHandler("tomorrow", handle_tomorrow))
    app.add_handler(CommandHandler("week", handle_week))
    app.add_handler(CommandHandler("twoweeks", handle_two_weeks))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("update", cmd_update))

    # --- ReplyKeyboard text buttons ---
    app.add_handler(MessageHandler(filters.Regex("^📅 Сегодня$"), handle_today))
    app.add_handler(MessageHandler(filters.Regex("^➡️ Завтра$"), handle_tomorrow))
    app.add_handler(MessageHandler(filters.Regex("^🗓 Неделя$"), handle_week))
    app.add_handler(MessageHandler(filters.Regex("^📖 2 недели$"), handle_two_weeks))

    # --- Text input: custom daily time (when waiting_for is set) ---
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_custom_time_input,
        )
    )

    # --- Inline callbacks ---
    app.add_handler(CallbackQueryHandler(cb_view,          pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(cb_group_selected, pattern=r"^grp:"))
    app.add_handler(CallbackQueryHandler(cb_settings,      pattern=r"^st:"))
    app.add_handler(CallbackQueryHandler(cb_start_hub,     pattern=r"^start:hub$"))

    # --- Jobs ---
    jq = app.job_queue
    if jq:
        jq.run_repeating(_stagger_job, interval=STAGGER_INTERVAL, first=30)
        jq.run_repeating(_daily_job,   interval=60,               first=60)
        logger.info(
            "Jobs scheduled: stagger every %ds, daily every 60s", STAGGER_INTERVAL
        )

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
