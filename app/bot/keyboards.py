"""Inline keyboard builders for Telegram bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def monitor_list_keyboard(monitors: list, page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    buttons = []
    for m in monitors:
        status = "⏸" if not m.is_active else "✅"
        if (m.consecutive_failures or 0) > 0:
            status = "⚠️"
        price = f"{float(m.last_price):.0f}" if m.last_price else "—"
        buttons.append([InlineKeyboardButton(
            f"{status} {m.name} | {price}",
            callback_data=f"detail_{m.id}",
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"list_page_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Далее ➡️", callback_data=f"list_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def monitor_actions_keyboard(monitor_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏸ Пауза" if is_active else "▶️ Возобновить"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(toggle_text, callback_data=f"toggle_{monitor_id}"),
            InlineKeyboardButton("🔄 Проверить", callback_data=f"check_{monitor_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{monitor_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{monitor_id}"),
        ],
        [InlineKeyboardButton("⬅️ К списку", callback_data="list_page_0")],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Интервал по умолчанию", callback_data="set_interval")],
        [InlineKeyboardButton("🌍 Часовой пояс", callback_data="set_timezone")],
        [InlineKeyboardButton("🌙 Тихие часы", callback_data="set_quiet_hours")],
        [InlineKeyboardButton("📬 Дайджест", callback_data="set_digest")],
    ])


def confirm_delete_keyboard(monitor_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{monitor_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"detail_{monitor_id}"),
        ],
    ])
