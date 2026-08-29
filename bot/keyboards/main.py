"""Keyboard layouts for the bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📅 Сегодня", "➡️ Завтра"],
            ["🗓 Неделя", "📖 2 недели"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )


def group_selection(groups: list) -> InlineKeyboardMarkup:
    """Inline keyboard with one button per group."""
    buttons = [
        [InlineKeyboardButton(
            text=g.name or g.external_id,
            callback_data=f"grp:{g.external_id}",
        )]
        for g in groups
    ]
    return InlineKeyboardMarkup(buttons)


def subgroup_selection() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("01 подгруппа", callback_data="sg:01"),
            InlineKeyboardButton("02 подгруппа", callback_data="sg:02"),
        ],
        [InlineKeyboardButton("Обе подгруппы", callback_data="sg:all")],
    ])


def settings_menu(
    change_notif_on: bool,
    subgroup: str | None,
) -> InlineKeyboardMarkup:
    notif_label = "🔔 Изменения: ВКЛ" if change_notif_on else "🔕 Изменения: ВЫКЛ"
    sg_label = f"👤 Подгруппа: {subgroup}" if subgroup else "👤 Подгруппа: Все"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(sg_label, callback_data="settings:subgroup")],
        [InlineKeyboardButton(notif_label, callback_data="settings:toggle_notif")],
        [InlineKeyboardButton("🔄 Сменить группу", callback_data="settings:change_group")],
    ])
