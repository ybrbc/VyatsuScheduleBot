"""Keyboard layouts.

UX design:
  - ReplyKeyboardMarkup (bottom bar): always present, quick schedule access.
  - InlineKeyboardMarkup: used for /start hub, settings, group/subgroup selection.
  - Settings are all in one inline message, edited in-place.
"""
from __future__ import annotations
from datetime import time
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from utils.formatter import DISPLAY_MODE_LABELS, DIFF_DISPLAY_MODE_LABELS


# ---------------------------------------------------------------------------
# Persistent bottom keyboard
# ---------------------------------------------------------------------------

def main_kb() -> ReplyKeyboardMarkup:
    """Always-visible keyboard for the most frequent actions."""
    return ReplyKeyboardMarkup(
        [
            ["📅 Сегодня", "➡️ Завтра"],
            ["🗓 Неделя", "📖 2 недели"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ---------------------------------------------------------------------------
# /start inline hub
# ---------------------------------------------------------------------------

def start_hub_kb(has_group: bool, group_name: Optional[str] = None) -> InlineKeyboardMarkup:
    """Inline message shown after /start."""
    if not has_group:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Выбрать группу", callback_data="st:change_group")]
        ])

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="view:today"),
            InlineKeyboardButton("➡️ Завтра", callback_data="view:tomorrow"),
        ],
        [
            InlineKeyboardButton("🗓 Неделя", callback_data="view:week"),
            InlineKeyboardButton("📖 2 недели", callback_data="view:two_weeks"),
        ],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="st:home")],
    ])


# ---------------------------------------------------------------------------
# Group selection
# ---------------------------------------------------------------------------

def group_selection_kb(groups: list, back_cb: str = "st:home") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            g.name or g.external_id,
            callback_data=f"grp:{g.external_id}:{back_cb}",
        )]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton("← Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Settings main screen
# ---------------------------------------------------------------------------

def settings_kb(user) -> InlineKeyboardMarkup:
    sg = user.subgroup
    sg_label = f"👤 Подгр.: {sg}" if sg else "👤 Подгр.: Все"

    dm = user.display_mode or "hide"
    dm_short = {"hide": "Скрыть", "strikethrough": "Зачерк.",
                "spoiler": "Спойлер", "spoiler_strikethrough": "Сп+зач."}
    dm_label = f"🎨 Вид подгр.: {dm_short.get(dm, dm)}"

    notif = user.change_notifications
    notif_label = "🔔 Изм.: ВКЛ" if notif else "🔕 Изм.: ВЫКЛ"

    ddm = user.diff_display_mode or "hide"
    ddm_short = {"hide": "Скрыть", "inline_strikethrough": "Зачерк.",
                 "inline_spoiler": "Спойлер", "separate": "Отдельно"}
    ddm_label = f"📢 Изм.подгр.: {ddm_short.get(ddm, ddm)}"

    if user.daily_notifications and user.daily_time:
        daily_label = f"⏰ Ежедн.: {user.daily_time.strftime('%H:%M')}"
    else:
        daily_label = "⏰ Ежедн.: Выкл"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(sg_label, callback_data="st:subgroup"),
         InlineKeyboardButton(dm_label, callback_data="st:display")],
        [InlineKeyboardButton(notif_label, callback_data="st:toggle_notif"),
         InlineKeyboardButton(ddm_label, callback_data="st:diff_display")],
        [InlineKeyboardButton(daily_label, callback_data="st:daily_time")],
        [InlineKeyboardButton("🔄 Сменить группу", callback_data="st:change_group")],
        [InlineKeyboardButton("← Назад", callback_data="start:hub")],
    ])


# ---------------------------------------------------------------------------
# Subgroup selection
# ---------------------------------------------------------------------------

def subgroup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("01 подгруппа", callback_data="st:set_sg:01"),
            InlineKeyboardButton("02 подгруппа", callback_data="st:set_sg:02"),
        ],
        [InlineKeyboardButton("Обе подгруппы", callback_data="st:set_sg:all")],
        [InlineKeyboardButton("← Назад", callback_data="st:home")],
    ])


# ---------------------------------------------------------------------------
# Display mode selection
# ---------------------------------------------------------------------------

def display_mode_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"st:set_dm:{key}")]
        for key, label in DISPLAY_MODE_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(buttons)


def diff_display_mode_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"st:set_ddm:{key}")]
        for key, label in DIFF_DISPLAY_MODE_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Daily time selection
# ---------------------------------------------------------------------------

_PRESET_TIMES = ["06:00", "07:00", "08:00", "09:00", "10:00",
                 "17:00", "18:00", "19:00", "20:00", "21:00"]


def daily_time_kb() -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for t in _PRESET_TIMES:
        row.append(InlineKeyboardButton(t, callback_data=f"st:set_dt:{t}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Своё время", callback_data="st:custom_time")])
    rows.append([InlineKeyboardButton("🚫 Отключить", callback_data="st:set_dt:off")])
    rows.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(rows)
