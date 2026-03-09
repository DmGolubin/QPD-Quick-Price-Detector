"""Inline keyboard callback handlers."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from app.database import async_session
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService, Pagination
from app.bot.formatters import format_monitor_card
from app.bot.keyboards import monitor_list_keyboard, monitor_actions_keyboard, confirm_delete_keyboard

logger = logging.getLogger(__name__)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ms = MonitorService(session)

        if data.startswith("list_page_"):
            page = int(data.split("_")[-1])
            result = await ms.list_monitors(user.id, pagination=Pagination(page + 1, 10))
            monitors = result["items"]
            total_pages = result["total_pages"]
            text = f"📋 <b>Мониторы</b> (стр. {page + 1}/{total_pages}):"
            if not monitors:
                text = "📭 Нет мониторов."
            keyboard = monitor_list_keyboard(monitors, page, total_pages)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        elif data.startswith("detail_"):
            monitor_id = int(data.split("_")[1])
            monitor = await ms.get_monitor(user.id, monitor_id)
            if not monitor:
                await query.edit_message_text("❌ Монитор не найден")
                return
            stats = await ms.get_price_stats(monitor_id)
            text = format_monitor_card(monitor, stats)
            keyboard = monitor_actions_keyboard(monitor_id, monitor.is_active)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        elif data.startswith("toggle_"):
            monitor_id = int(data.split("_")[1])
            monitor = await ms.toggle_monitor(user.id, monitor_id)
            if monitor:
                status = "▶️ Возобновлён" if monitor.is_active else "⏸ Приостановлен"
                stats = await ms.get_price_stats(monitor_id)
                text = f"{status}\n\n{format_monitor_card(monitor, stats)}"
                keyboard = monitor_actions_keyboard(monitor_id, monitor.is_active)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        elif data.startswith("delete_") and not data.startswith("delete_confirm"):
            monitor_id = int(data.split("_")[1])
            await query.edit_message_text(
                "⚠️ Удалить монитор и всю историю цен?",
                reply_markup=confirm_delete_keyboard(monitor_id),
            )

        elif data.startswith("confirm_delete_"):
            monitor_id = int(data.split("_")[-1])
            if await ms.delete_monitor(user.id, monitor_id):
                await query.edit_message_text("🗑 Монитор удалён.")
            else:
                await query.edit_message_text("❌ Монитор не найден.")

        elif data.startswith("check_"):
            monitor_id = int(data.split("_")[1])
            await query.edit_message_text("🔄 Проверка запущена...")
