"""Keyboard layouts."""
from __future__ import annotations
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from utils.formatter import DISPLAY_MODE_LABELS, DIFF_DISPLAY_MODE_LABELS


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["📅 Сегодня", "➡️ Завтра"], ["🗓 Неделя", "📖 2 недели"],
         ["🗒 Следующая неделя", "📊 Прогресс"]],
        resize_keyboard=True, is_persistent=False,
    )


def start_hub_kb(has_group: bool, group_name: Optional[str] = None) -> InlineKeyboardMarkup:
    if not has_group:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Выбрать группу", callback_data="st:change_group")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Сегодня",   callback_data="view:today"),
         InlineKeyboardButton("➡️ Завтра",    callback_data="view:tomorrow")],
        [InlineKeyboardButton("🗓 Неделя",    callback_data="view:week"),
         InlineKeyboardButton("📖 2 недели",  callback_data="view:two_weeks")],
        [InlineKeyboardButton("📊 Прогресс", callback_data="progress")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="st:home")],
    ])


def group_selection_kb(groups: list, back_cb: str = "st:home") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(g.name or g.external_id,
                              callback_data=f"grp:{g.external_id}:{back_cb}")]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton("← Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)


def settings_kb(user) -> InlineKeyboardMarkup:
    sg = user.subgroup
    sg_label = f"👤 Подгр.: {sg}" if sg else "👤 Подгр.: Все"

    dm = user.display_mode or "hide"
    dm_short = {"hide": "Скрыть", "strikethrough": "Зачерк.",
                "spoiler": "Спойлер", "spoiler_strikethrough": "Сп+зач."}
    dm_label = f"🎨 Вид подгр.: {dm_short.get(dm, dm)}"

    notif_label = "🔔 Изм.: ВКЛ" if user.change_notifications else "🔕 Изм.: ВЫКЛ"

    ddm = user.diff_display_mode or "hide"
    ddm_short = {"hide": "Скрыть", "inline_strikethrough": "Зачерк.",
                 "inline_spoiler": "Спойлер", "separate": "Отдельно"}
    ddm_label = f"📢 Изм.подгр.: {ddm_short.get(ddm, ddm)}"

    daily_label = (
        f"⏰ Ежедн.: {user.daily_time.strftime('%H:%M')}"
        if user.daily_notifications and user.daily_time else "⏰ Ежедн.: Выкл"
    )
    # Show which day the notification sends for
    daily_day = "завтра" if getattr(user, "daily_send_tomorrow", False) else "сегодня"
    daily_day_label = f"📅 Отправлять: на {daily_day}"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(sg_label,    callback_data="st:subgroup"),
         InlineKeyboardButton(dm_label,    callback_data="st:display")],
        [InlineKeyboardButton(notif_label, callback_data="st:toggle_notif"),
         InlineKeyboardButton(ddm_label,   callback_data="st:diff_display")],
        [InlineKeyboardButton(daily_label,     callback_data="st:daily_time"),
         InlineKeyboardButton(daily_day_label, callback_data="st:toggle_daily_tomorrow")],
        [InlineKeyboardButton("📌 Всегда показывать", callback_data="sf:list:always_show"),
         InlineKeyboardButton("🚫 Всегда скрывать",  callback_data="sf:list:never_show")],
        [InlineKeyboardButton("🔄 Сменить группу",   callback_data="st:change_group")],
        [InlineKeyboardButton("← Назад",             callback_data="start:hub")],
    ])


def subgroup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("01 подгруппа", callback_data="st:set_sg:01"),
         InlineKeyboardButton("02 подгруппа", callback_data="st:set_sg:02")],
        [InlineKeyboardButton("Обе подгруппы", callback_data="st:set_sg:all")],
        [InlineKeyboardButton("← Назад", callback_data="st:home")],
    ])


def display_mode_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"st:set_dm:{key}")]
        for key, label in DISPLAY_MODE_LABELS.items()
    ]
    rows.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(rows)


def diff_display_mode_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"st:set_ddm:{key}")]
        for key, label in DIFF_DISPLAY_MODE_LABELS.items()
    ]
    rows.append([InlineKeyboardButton("← Назад", callback_data="st:home")])
    return InlineKeyboardMarkup(rows)


_PRESET_TIMES = ["06:00", "07:00", "08:00", "09:00", "10:00",
                 "17:00", "18:00", "19:00", "20:00", "21:00"]


def daily_time_kb(send_tomorrow: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for t in _PRESET_TIMES:
        row.append(InlineKeyboardButton(t, callback_data=f"st:set_dt:{t}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row:
        rows.append(row)

    # Toggle: which day to send
    day_label = "📅 Для: Завтра" if send_tomorrow else "📅 Для: Сегодня"
    rows.append([InlineKeyboardButton(
        day_label, callback_data="st:toggle_daily_tomorrow_dt"
    )])
    rows.append([InlineKeyboardButton("✏️ Своё время", callback_data="st:custom_time")])
    rows.append([InlineKeyboardButton("🚫 Отключить",  callback_data="st:set_dt:off")])
    rows.append([InlineKeyboardButton("← Назад",       callback_data="st:home")])
    return InlineKeyboardMarkup(rows)
