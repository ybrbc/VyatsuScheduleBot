"""Settings handler — all navigation edits a single inline message in-place.

Callback pattern: "st:{action}" or "st:{action}:{value}"
  st:home           → show main settings screen
  st:subgroup       → show subgroup selection
  st:set_sg:{val}   → set subgroup, return to home
  st:display        → show display-mode screen
  st:set_dm:{mode}  → set display mode, return to home
  st:diff_display   → show diff-display-mode screen
  st:set_ddm:{mode} → set diff display mode, return to home
  st:toggle_notif   → toggle change_notifications, return to home
  st:daily_time     → show time picker
  st:set_dt:{time}  → set daily time (HH:MM or "off"), return to home
  st:custom_time    → ask user to type a time, save state
  st:change_group   → show group selection
"""
from __future__ import annotations
import asyncio
import logging
import re
from datetime import time
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.keyboards.main import (
    daily_time_kb, diff_display_mode_kb, display_mode_kb,
    group_selection_kb, settings_kb, subgroup_kb,
)
from database.connection import get_session
from repositories import group_repository as gr
from repositories import user_repository as ur

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


# ---------------------------------------------------------------------------
# Public: build settings text + keyboard (used by other handlers too)
# ---------------------------------------------------------------------------

def _build_settings_msg(tg_id: int):
    """Synchronous — call via asyncio.to_thread from async contexts."""
    with get_session() as s:
        user, _ = ur.get_or_create(s, tg_id)
        grp = user.group
        group_name = (grp.name if grp else None) or "—"
        sg = user.subgroup or "Все"
        return (
            f"⚙️ <b>Настройки</b>\n\n"
            f"📚 Группа: <b>{group_name}</b>\n"
            f"👤 Подгруппа: <b>{sg}</b>",
            settings_kb(user),
        )


# ---------------------------------------------------------------------------
# /settings command
# ---------------------------------------------------------------------------

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Main callback dispatcher
# ---------------------------------------------------------------------------

async def cb_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data              # "st:home", "st:set_sg:01", etc.
    parts = data.split(":", 2)
    action = parts[1] if len(parts) > 1 else "home"
    value = parts[2] if len(parts) > 2 else ""
    tg_id = update.effective_user.id

    # ---- Navigation ----
    if action == "home":
        await _show_settings(query, tg_id)

    elif action == "subgroup":
        await query.edit_message_text(
            "👤 <b>Выберите подгруппу</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=subgroup_kb(),
        )

    elif action == "set_sg":
        sg = None if value == "all" else value
        await asyncio.to_thread(_do, ur.set_subgroup, tg_id, sg)
        await _show_settings(query, tg_id)

    elif action == "display":
        await query.edit_message_text(
            "🎨 <b>Отображение пар другой подгруппы в расписании</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=display_mode_kb(),
        )

    elif action == "set_dm":
        await asyncio.to_thread(_do, ur.set_display_mode, tg_id, value)
        await _show_settings(query, tg_id)

    elif action == "diff_display":
        await query.edit_message_text(
            "📢 <b>Показывать изменения другой подгруппы в уведомлениях</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=diff_display_mode_kb(),
        )

    elif action == "set_ddm":
        await asyncio.to_thread(_do, ur.set_diff_display_mode, tg_id, value)
        await _show_settings(query, tg_id)

    elif action == "toggle_notif":
        def _toggle():
            with get_session() as s:
                user, _ = ur.get_or_create(s, tg_id)
                ur.set_change_notifications(s, tg_id, not user.change_notifications)
        await asyncio.to_thread(_toggle)
        await _show_settings(query, tg_id)

    elif action == "daily_time":
        await query.edit_message_text(
            "⏰ <b>Выберите время ежедневного расписания</b>\n\n"
            "Каждый день в выбранное время бот пришлёт расписание на сегодня.",
            parse_mode=ParseMode.HTML,
            reply_markup=daily_time_kb(),
        )

    elif action == "set_dt":
        if value == "off":
            await asyncio.to_thread(_do, ur.set_daily_time, tg_id, None, False)
        else:
            t = _parse_time(value)
            if t:
                await asyncio.to_thread(_do, ur.set_daily_time, tg_id, t, True)
        await _show_settings(query, tg_id)

    elif action == "custom_time":
        # Save state: waiting for text input
        ctx.user_data["waiting_for"] = "daily_time"
        ctx.user_data["settings_chat"] = query.message.chat_id
        ctx.user_data["settings_msg_id"] = query.message.message_id
        await query.edit_message_text(
            "⏰ Введите время в формате <b>ЧЧ:ММ</b>\n"
            "Например: <code>08:30</code>",
            parse_mode=ParseMode.HTML,
        )

    elif action == "change_group":
        def _groups():
            with get_session() as s:
                return gr.get_active(s)
        groups = await asyncio.to_thread(_groups)
        await query.edit_message_text(
            "🔄 <b>Выберите группу</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=group_selection_kb(groups, back_cb="st:home"),
        )


# ---------------------------------------------------------------------------
# Handle freeform text when waiting for custom time input
# ---------------------------------------------------------------------------

async def handle_custom_time_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when user_data['waiting_for'] == 'daily_time'."""
    if ctx.user_data.get("waiting_for") != "daily_time":
        return  # Not our message — let it fall through

    tg_id = update.effective_user.id
    text = update.message.text.strip()
    t = _parse_time(text)

    if t is None:
        await update.message.reply_text(
            "⚠️ Неверный формат. Введите время как <b>ЧЧ:ММ</b> (например, <code>08:30</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    await asyncio.to_thread(_do, ur.set_daily_time, tg_id, t, True)
    ctx.user_data.pop("waiting_for", None)

    # Rebuild settings and send as new message (original was replaced by text prompt)
    text_msg, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await update.message.reply_text(
        f"✅ Время установлено: <b>{t.strftime('%H:%M')}</b>\n\n" + text_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _show_settings(query, tg_id: int) -> None:
    text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


def _do(fn, *args):
    """Run a repository function inside a session."""
    with get_session() as s:
        fn(s, *args)


def _parse_time(raw: str) -> Optional[time]:
    m = _TIME_RE.match(raw.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return time(h, mi)
    return None
