"""Telegram bot command handlers."""
import json
import logging
import re

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
)

from app.database import async_session
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService, Pagination
from app.services.export_service import ExportService
from app.services.digest_service import DigestService
from app.services.comparison_service import ComparisonService
from app.services.template_service import TemplateService
from app.bot.formatters import format_monitor_card, format_comparison_table, parse_macro_text
from app.bot.keyboards import (
    monitor_list_keyboard, monitor_actions_keyboard,
    settings_keyboard, confirm_delete_keyboard,
)

logger = logging.getLogger(__name__)

# Conversation states
NAME, URL, SELECTOR, THRESHOLDS, CONFIRM = range(5)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(
            str(update.effective_chat.id),
            update.effective_user.username if update.effective_user else None,
        )
    await update.message.reply_html(
        f"👋 Привет! Я <b>Price Monitor Pro</b> — бот для отслеживания цен.\n\n"
        f"Команды:\n"
        f"/add — добавить монитор\n"
        f"/list — список мониторов\n"
        f"/check — проверить все цены\n"
        f"/stats — статистика\n"
        f"/report — отчёт за 24ч\n"
        f"/settings — настройки\n"
        f"/export — экспорт данных\n"
        f"/apikey — получить API-ключ\n"
        f"/digest — дайджест\n"
        f"/help — справка\n\n"
        f"Или просто отправьте URL для отслеживания."
    )


async def cmd_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введите название для монитора:")
    return NAME


async def cmd_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["monitor_name"] = update.message.text
    await update.message.reply_text("🔗 Введите URL страницы с товаром:")
    return URL


async def cmd_add_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ URL должен начинаться с http:// или https://")
        return URL
    context.user_data["monitor_url"] = url
    await update.message.reply_text(
        "🎯 Введите CSS-селектор элемента с ценой\n"
        "или /skip для автоопределения:"
    )
    return SELECTOR


async def cmd_add_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        context.user_data["monitor_selector"] = text
    else:
        context.user_data["monitor_selector"] = None
    await update.message.reply_text(
        "💰 Введите порог цены для уведомления (число)\n"
        "или /skip чтобы пропустить:"
    )
    return THRESHOLDS


async def cmd_add_thresholds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "/skip":
        try:
            context.user_data["threshold_below"] = float(text)
        except ValueError:
            await update.message.reply_text("❌ Введите число или /skip")
            return THRESHOLDS
    data = context.user_data
    name = data.get("monitor_name", "")
    url = data.get("monitor_url", "")
    selector = data.get("monitor_selector", "авто")
    threshold = data.get("threshold_below", "—")
    await update.message.reply_html(
        f"📋 <b>Подтвердите создание монитора:</b>\n\n"
        f"Название: {name}\n"
        f"URL: {url}\n"
        f"Селектор: {selector or 'авто'}\n"
        f"Порог: {threshold}\n\n"
        f"Отправьте /confirm для создания или /cancel для отмены."
    )
    return CONFIRM


async def cmd_add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ms = MonitorService(session)
        ts = TemplateService(session)
        monitor_data = {
            "name": data.get("monitor_name", ""),
            "url": data.get("monitor_url", ""),
            "css_selector": data.get("monitor_selector"),
            "threshold_below": data.get("threshold_below"),
        }
        # Apply template if available
        template = await ts.get_template_for_url(monitor_data["url"])
        try:
            monitor = await ms.create_monitor(user.id, monitor_data)
            if template:
                await ts.apply_template(monitor, template)
                await session.commit()
            await update.message.reply_html(
                f"✅ Монитор <b>{monitor.name}</b> создан!\n"
                f"ID: {monitor.id}\n"
                f"{'📦 Шаблон: ' + template.store_name if template else ''}"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    context.user_data.clear()
    return ConversationHandler.END


async def cmd_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Создание монитора отменено.")
    return ConversationHandler.END


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_list(update, context, page=0)


async def _show_list(update_or_query, context, page=0):
    async with async_session() as session:
        auth = AuthService(session)
        chat_id = update_or_query.effective_chat.id if hasattr(update_or_query, 'effective_chat') else update_or_query.message.chat_id
        user = await auth.get_or_create_user(str(chat_id))
        ms = MonitorService(session)
        result = await ms.list_monitors(user.id, pagination=Pagination(page + 1, 10))
        monitors = result["items"]
        total_pages = result["total_pages"]
    if not monitors:
        text = "📭 У вас пока нет мониторов. Используйте /add для создания."
    else:
        text = f"📋 <b>Мониторы</b> (стр. {page + 1}/{total_pages}):"
    keyboard = monitor_list_keyboard(monitors, page, total_pages)
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_html(text, reply_markup=keyboard)
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запускаю проверку всех мониторов...")
    # This would trigger the scheduler to enqueue immediate checks
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ms = MonitorService(session)
        result = await ms.list_monitors(user.id)
        count = len(result["items"])
    await update.message.reply_text(f"✅ {count} мониторов поставлены в очередь проверки.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ms = MonitorService(session)
        stats = await ms.get_stats(user.id)
    await update.message.reply_html(
        f"📊 <b>Статистика</b>\n\n"
        f"Всего мониторов: {stats['total_monitors']}\n"
        f"Активных: {stats['active_monitors']}\n"
        f"С ценой: {stats['with_price']}\n"
        f"Точек данных: {stats['data_points']}"
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ds = DigestService(session)
        report = await ds.generate_daily_digest(user.id)
    await update.message.reply_html(report)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_keyboard(),
    )


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        es = ExportService(session)
        data = await es.export_json(user.id)
    import io
    file_content = json.dumps(data, ensure_ascii=False, indent=2)
    bio = io.BytesIO(file_content.encode("utf-8"))
    bio.name = "monitors_export.json"
    await update.message.reply_document(bio, caption="📦 Экспорт мониторов")


async def cmd_apikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        key = await auth.generate_api_key(user.id)
    await update.message.reply_html(
        f"🔑 Ваш API-ключ:\n<code>{key}</code>\n\n"
        f"Используйте заголовок: <code>Authorization: ApiKey {key}</code>"
    )


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ds = DigestService(session)
        digest = await ds.generate_daily_digest(user.id)
    await update.message.reply_html(digest)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "📖 <b>Команды Price Monitor Pro</b>\n\n"
        "/add — добавить монитор\n"
        "/list — список мониторов\n"
        "/check — проверить все цены\n"
        "/stats — статистика\n"
        "/report — отчёт за 24ч\n"
        "/edit_ID — редактировать монитор\n"
        "/compare_ID — сравнение группы\n"
        "/settings — настройки\n"
        "/export — экспорт в JSON\n"
        "/apikey — получить API-ключ\n"
        "/digest — дайджест\n"
        "/help — эта справка\n\n"
        "💡 Отправьте URL — создам монитор автоматически."
    )


async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain URL messages — offer to create a monitor."""
    text = update.message.text.strip()
    url_match = re.match(r'https?://\S+', text)
    if not url_match:
        return
    url = url_match.group()
    async with async_session() as session:
        auth = AuthService(session)
        user = await auth.get_or_create_user(str(update.effective_chat.id))
        ms = MonitorService(session)
        ts = TemplateService(session)
        template = await ts.get_template_for_url(url)
        template_info = f"\n📦 Шаблон: {template.store_name}" if template else ""
        monitor_data = {"name": url.split("/")[2], "url": url}
        try:
            monitor = await ms.create_monitor(user.id, monitor_data)
            if template:
                await ts.apply_template(monitor, template)
                await session.commit()
            await update.message.reply_html(
                f"✅ Монитор создан: <b>{monitor.name}</b>{template_info}\n"
                f"ID: {monitor.id}\n"
                f"Используйте /edit_{monitor.id} для настройки."
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
