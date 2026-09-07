"""Settings handler — all navigation edits a single inline message in-place."""
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


def _build_settings_msg(tg_id: int):
    with get_session() as s:
        user, _ = ur.get_or_create(s, tg_id)
        grp = user.group
        group_name = (grp.name if grp else None) or "—"
        sg = user.subgroup or "Все"

        daily_info = ""
        if user.daily_notifications and user.daily_time:
            day_label = "завтра" if user.daily_send_tomorrow else "сегодня"
            daily_info = (
                f"\n⏰ Ежедн.: {user.daily_time.strftime('%H:%M')} "
                f"(расписание на {day_label})"
            )

        return (
            f"⚙️ <b>Настройки</b>\n\n"
            f"📚 Группа: <b>{group_name}</b>\n"
            f"👤 Подгруппа: <b>{sg}</b>"
            f"{daily_info}",
            settings_kb(user),
        )


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = update.effective_user.id
    text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cb_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    action = parts[1] if len(parts) > 1 else "home"
    value  = parts[2] if len(parts) > 2 else ""
    tg_id  = update.effective_user.id

    # ── Navigation ──────────────────────────────────────────────────────────
    if action == "home":
        await _show_settings(query, tg_id)

    elif action == "subgroup":
        await query.edit_message_text(
            "👤 <b>Выберите подгруппу</b>",
            parse_mode=ParseMode.HTML, reply_markup=subgroup_kb(),
        )

    elif action == "set_sg":
        sg = None if value == "all" else value
        def _s():
            with get_session() as s: ur.set_subgroup(s, tg_id, sg)
        await asyncio.to_thread(_s)
        await _show_settings(query, tg_id)

    elif action == "display":
        await query.edit_message_text(
            "🎨 <b>Отображение пар другой подгруппы</b>",
            parse_mode=ParseMode.HTML, reply_markup=display_mode_kb(),
        )

    elif action == "set_dm":
        def _s():
            with get_session() as s: ur.set_display_mode(s, tg_id, value)
        await asyncio.to_thread(_s)
        await _show_settings(query, tg_id)

    elif action == "diff_display":
        await query.edit_message_text(
            "📢 <b>Изменения другой подгруппы в уведомлениях</b>",
            parse_mode=ParseMode.HTML, reply_markup=diff_display_mode_kb(),
        )

    elif action == "set_ddm":
        def _s():
            with get_session() as s: ur.set_diff_display_mode(s, tg_id, value)
        await asyncio.to_thread(_s)
        await _show_settings(query, tg_id)

    elif action == "toggle_notif":
        def _toggle():
            with get_session() as s:
                user, _ = ur.get_or_create(s, tg_id)
                ur.set_change_notifications(s, tg_id, not user.change_notifications)
        await asyncio.to_thread(_toggle)
        await _show_settings(query, tg_id)

    # ── Daily time ───────────────────────────────────────────────────────────
    elif action == "daily_time":
        def _get_tomorrow():
            with get_session() as s:
                user, _ = ur.get_or_create(s, tg_id)
                return bool(user.daily_send_tomorrow)
        send_tomorrow = await asyncio.to_thread(_get_tomorrow)
        await query.edit_message_text(
            "⏰ <b>Ежедневное расписание</b>\n\n"
            "Выберите время отправки и для какого дня.",
            parse_mode=ParseMode.HTML,
            reply_markup=daily_time_kb(send_tomorrow),
        )

    elif action == "set_dt":
        if value == "off":
            def _s():
                with get_session() as s: ur.set_daily_time(s, tg_id, None, False)
            await asyncio.to_thread(_s)
        else:
            t = _parse_time(value)
            if t:
                def _s():
                    with get_session() as s: ur.set_daily_time(s, tg_id, t, True)
                await asyncio.to_thread(_s)
        await _show_settings(query, tg_id)

    elif action in ("toggle_daily_tomorrow", "toggle_daily_tomorrow_dt"):
        # Toggle the send_tomorrow flag
        def _toggle_tomorrow():
            with get_session() as s:
                user, _ = ur.get_or_create(s, tg_id)
                ur.set_daily_send_tomorrow(s, tg_id, not user.daily_send_tomorrow)
                return bool(user.daily_send_tomorrow)  # returns OLD value before toggle
        old = await asyncio.to_thread(_toggle_tomorrow)
        new_val = not old

        if action == "toggle_daily_tomorrow_dt":
            # Stay in daily_time screen, refresh keyboard
            await query.edit_message_text(
                "⏰ <b>Ежедневное расписание</b>\n\n"
                "Выберите время отправки и для какого дня.",
                parse_mode=ParseMode.HTML,
                reply_markup=daily_time_kb(new_val),
            )
        else:
            # Toggled from main settings — return to settings
            await _show_settings(query, tg_id)

    elif action == "custom_time":
        ctx.user_data["waiting_for"] = "daily_time"
        ctx.user_data["settings_msg_id"] = query.message.message_id
        await query.edit_message_text(
            "⏰ Введите время в формате <b>ЧЧ:ММ</b>\nНапример: <code>08:30</code>",
            parse_mode=ParseMode.HTML,
        )

    elif action == "change_group":
        def _g():
            with get_session() as s: return gr.get_active(s)
        groups = await asyncio.to_thread(_g)
        await query.edit_message_text(
            "🔄 <b>Выберите группу</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=group_selection_kb(groups, back_cb="st:home"),
        )


async def handle_custom_time_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("waiting_for") != "daily_time":
        return
    tg_id = update.effective_user.id
    t = _parse_time(update.message.text.strip())
    if t is None:
        await update.message.reply_text(
            "⚠️ Неверный формат. Введите как <b>ЧЧ:ММ</b> (например, <code>08:30</code>).",
            parse_mode=ParseMode.HTML,
        )
        return
    def _s():
        with get_session() as s: ur.set_daily_time(s, tg_id, t, True)
    await asyncio.to_thread(_s)
    ctx.user_data.pop("waiting_for", None)
    text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await update.message.reply_text(
        f"✅ Время: <b>{t.strftime('%H:%M')}</b>\n\n" + text,
        parse_mode=ParseMode.HTML, reply_markup=kb,
    )


async def _show_settings(query, tg_id: int) -> None:
    text, kb = await asyncio.to_thread(_build_settings_msg, tg_id)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


def _parse_time(raw: str) -> Optional[time]:
    m = _TIME_RE.match(raw.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return time(h, mi) if 0 <= h <= 23 and 0 <= mi <= 59 else None
