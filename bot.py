import logging
import asyncio
from datetime import datetime, timedelta

import httpx
import psycopg2.extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import get_conn
from scraper import scrape_price, parse_price

logger = logging.getLogger("price-tracker.bot")

# Conversation states
NAME, URL, SELECTOR, THRESHOLDS = range(4)

# Temp storage for add flow
_pending = {}


async def send_notification(message: str):
    """Send alert to configured chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
        except Exception as e:
            logger.error(f"Telegram send error: {e}")


# --- Command Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏷 <b>Price Tracker Bot</b>\n\n"
        "Отслеживаю цены на любых сайтах и уведомляю об изменениях.\n\n"
        "📋 <b>Команды:</b>\n"
        "/add — добавить товар\n"
        "/list — список отслеживаемых\n"
        "/check — проверить цены сейчас\n"
        "/stats — статистика\n"
        "/help — помощь\n",
        parse_mode="HTML"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как пользоваться:</b>\n\n"
        "1️⃣ <b>/add</b> — добавляешь товар:\n"
        "   • Название (для себя)\n"
        "   • URL страницы товара\n"
        "   • CSS-селектор цены (опционально)\n"
        "   • Пороги уведомлений (опционально)\n\n"
        "2️⃣ Бот автоматически проверяет цены каждые 5 минут\n\n"
        "3️⃣ Получаешь уведомления когда:\n"
        "   📉 Цена снизилась\n"
        "   📈 Цена выросла\n"
        "   🔔 Цена ниже/выше порога\n\n"
        "💡 <b>CSS-селекторы:</b>\n"
        "Если не указать — бот попробует найти цену автоматически.\n"
        "Примеры: <code>.price</code>, <code>span[data-auto=\"price\"]</code>\n\n"
        "🌐 Веб-дашборд с графиками доступен по ссылке сервиса.",
        parse_mode="HTML"
    )


# --- Add Watch Conversation ---

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _pending[update.effective_user.id] = {}
    await update.message.reply_text(
        "📝 <b>Добавление товара</b>\n\nВведи название (например: iPhone 15 Pro Ozon):",
        parse_mode="HTML"
    )
    return NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _pending[uid]["name"] = update.message.text.strip()
    await update.message.reply_text("🔗 Теперь отправь URL страницы товара:")
    return URL


async def add_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ URL должен начинаться с http:// или https://")
        return URL
    _pending[uid]["url"] = url
    await update.message.reply_text(
        "🎯 CSS-селектор элемента с ценой.\n\n"
        "Примеры:\n"
        "• <code>.price-value</code>\n"
        "• <code>span[data-auto=\"price\"]</code>\n"
        "• <code>#product-price</code>\n\n"
        "Отправь селектор или /skip для автоопределения:",
        parse_mode="HTML"
    )
    return SELECTOR


async def add_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    if text != "/skip":
        _pending[uid]["css_selector"] = text
    else:
        _pending[uid]["css_selector"] = None

    await update.message.reply_text(
        "💰 Пороги уведомлений (опционально).\n\n"
        "Формат: <code>мин макс</code>\n"
        "Пример: <code>50000 100000</code> — уведомит если цена ниже 50к или выше 100к\n\n"
        "Отправь пороги или /skip:",
        parse_mode="HTML"
    )
    return THRESHOLDS


async def add_thresholds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    data = _pending.get(uid, {})

    threshold_below = None
    threshold_above = None

    if text != "/skip":
        parts = text.split()
        try:
            if len(parts) >= 1:
                threshold_below = float(parts[0])
            if len(parts) >= 2:
                threshold_above = float(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Пример: <code>50000 100000</code> или /skip", parse_mode="HTML")
            return THRESHOLDS

    # Save to DB
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """INSERT INTO watches (name, url, css_selector, threshold_below, threshold_above)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (data["name"], data["url"], data.get("css_selector"), threshold_below, threshold_above)
    )
    watch = cur.fetchone()
    cur.close()
    conn.close()

    _pending.pop(uid, None)

    # Try first scrape
    msg = await update.message.reply_text("⏳ Проверяю цену...")
    result = await scrape_price(data["url"], data.get("css_selector"))

    if result["price"] is not None:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO price_history (watch_id, price, raw_text) VALUES (%s, %s, %s)",
            (watch["id"], result["price"], result["raw_text"])
        )
        cur.execute(
            "UPDATE watches SET last_price = %s, last_checked = NOW() WHERE id = %s",
            (result["price"], watch["id"])
        )
        cur.close()
        conn.close()
        await msg.edit_text(
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📦 {data['name']}\n"
            f"💰 Текущая цена: <b>{result['price']:.2f} ₽</b>\n"
            f"🔗 {data['url'][:60]}...\n"
            f"{'🔔 Порог ↓: ' + str(threshold_below) if threshold_below else ''}\n"
            f"{'⚠️ Порог ↑: ' + str(threshold_above) if threshold_above else ''}",
            parse_mode="HTML"
        )
    else:
        err = result.get("error", "Не удалось определить цену автоматически")
        await msg.edit_text(
            f"⚠️ <b>Товар добавлен, но цена не определена</b>\n\n"
            f"📦 {data['name']}\n"
            f"Ошибка: {err}\n\n"
            f"Попробуй указать CSS-селектор точнее через /edit_{watch['id']}",
            parse_mode="HTML"
        )

    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _pending.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Добавление отменено.")
    return ConversationHandler.END


# --- List / Check / Stats ---

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches ORDER BY created_at DESC")
    watches = cur.fetchall()
    cur.close()
    conn.close()

    if not watches:
        await update.message.reply_text("📭 Список пуст. Добавь товар через /add")
        return

    lines = ["📋 <b>Отслеживаемые товары:</b>\n"]
    for w in watches:
        status = "✅" if w["is_active"] else "⏸"
        price_str = f"{float(w['last_price']):.2f} ₽" if w["last_price"] else "—"
        lines.append(
            f"{status} <b>{w['name']}</b>\n"
            f"   💰 {price_str}\n"
            f"   🆔 /detail_{w['id']}"
        )

    keyboard = []
    for w in watches:
        row = [
            InlineKeyboardButton(
                f"{'⏸' if w['is_active'] else '▶️'} {w['name'][:20]}",
                callback_data=f"toggle_{w['id']}"
            ),
            InlineKeyboardButton("🗑", callback_data=f"delete_{w['id']}")
        ]
        keyboard.append(row)

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches WHERE is_active = true")
    watches = cur.fetchall()
    cur.close()
    conn.close()

    if not watches:
        await update.message.reply_text("📭 Нет активных товаров.")
        return

    msg = await update.message.reply_text(f"⏳ Проверяю {len(watches)} товаров...")

    results = []
    for w in watches:
        r = await scrape_price(w["url"], w["css_selector"])
        old_price = float(w["last_price"]) if w["last_price"] else None

        if r["price"] is not None:
            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute(
                "INSERT INTO price_history (watch_id, price, raw_text) VALUES (%s, %s, %s)",
                (w["id"], r["price"], r["raw_text"])
            )
            cur2.execute(
                "UPDATE watches SET last_price = %s, last_checked = NOW() WHERE id = %s",
                (r["price"], w["id"])
            )
            cur2.close()
            conn2.close()

            diff_str = ""
            if old_price and r["price"] != old_price:
                diff = r["price"] - old_price
                pct = (diff / old_price) * 100
                emoji = "📈" if diff > 0 else "📉"
                diff_str = f" {emoji} {diff:+.2f} ({pct:+.1f}%)"

            results.append(f"✅ {w['name']}: {r['price']:.2f} ₽{diff_str}")
        else:
            results.append(f"❌ {w['name']}: ошибка")

    await msg.edit_text(
        "📊 <b>Результаты проверки:</b>\n\n" + "\n".join(results),
        parse_mode="HTML"
    )


async def cmd_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        watch_id = int(text.split("_")[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Формат: /detail_ID")
        return

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches WHERE id = %s", (watch_id,))
    w = cur.fetchone()
    if not w:
        await update.message.reply_text("❌ Товар не найден")
        cur.close()
        conn.close()
        return

    cur.execute(
        "SELECT price, recorded_at FROM price_history WHERE watch_id = %s ORDER BY recorded_at DESC LIMIT 20",
        (watch_id,)
    )
    history = cur.fetchall()

    cur.execute(
        "SELECT MIN(price) as min_p, MAX(price) as max_p, AVG(price) as avg_p, COUNT(*) as cnt "
        "FROM price_history WHERE watch_id = %s",
        (watch_id,)
    )
    stats = cur.fetchone()
    cur.close()
    conn.close()

    history_lines = []
    for h in history[:10]:
        history_lines.append(f"  {h['recorded_at'].strftime('%d.%m %H:%M')} — {float(h['price']):.2f} ₽")

    msg = (
        f"📦 <b>{w['name']}</b>\n"
        f"🔗 {w['url'][:60]}...\n"
        f"{'✅ Активно' if w['is_active'] else '⏸ На паузе'}\n\n"
        f"💰 Текущая: <b>{float(w['last_price']):.2f} ₽</b>\n" if w['last_price'] else f"💰 Нет данных\n"
    )
    if stats and stats["cnt"]:
        msg += (
            f"📊 Мин: {float(stats['min_p']):.2f} | Макс: {float(stats['max_p']):.2f} | "
            f"Сред: {float(stats['avg_p']):.2f}\n"
            f"📈 Точек данных: {stats['cnt']}\n"
        )
    if w["threshold_below"]:
        msg += f"🔔 Порог ↓: {w['threshold_below']} ₽\n"
    if w["threshold_above"]:
        msg += f"⚠️ Порог ↑: {w['threshold_above']} ₽\n"
    if history_lines:
        msg += f"\n📜 <b>Последние записи:</b>\n" + "\n".join(history_lines)

    keyboard = [
        [
            InlineKeyboardButton("🔄 Проверить", callback_data=f"recheck_{watch_id}"),
            InlineKeyboardButton("⏸ Пауза" if w["is_active"] else "▶️ Вкл", callback_data=f"toggle_{watch_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{watch_id}"),
        ]
    ]

    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_active) as active FROM watches")
    w_stats = cur.fetchone()
    cur.execute("SELECT COUNT(*) as total FROM price_history")
    p_stats = cur.fetchone()
    cur.execute("SELECT COUNT(*) as total FROM alerts_log")
    a_stats = cur.fetchone()
    cur.close()
    conn.close()

    await update.message.reply_text(
        f"📊 <b>Статистика</b>\n\n"
        f"📦 Товаров: {w_stats['total']} (активных: {w_stats['active']})\n"
        f"📈 Записей цен: {p_stats['total']}\n"
        f"🔔 Алертов: {a_stats['total']}",
        parse_mode="HTML"
    )


# --- Callback Query Handler ---

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("toggle_"):
        watch_id = int(data.split("_")[1])
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("UPDATE watches SET is_active = NOT is_active, updated_at = NOW() WHERE id = %s RETURNING is_active, name", (watch_id,))
        result = cur.fetchone()
        cur.close()
        conn.close()
        if result:
            status = "✅ активирован" if result["is_active"] else "⏸ приостановлен"
            await query.edit_message_text(f"{result['name']} — {status}")

    elif data.startswith("delete_"):
        watch_id = int(data.split("_")[1])
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT name FROM watches WHERE id = %s", (watch_id,))
        w = cur.fetchone()
        cur.execute("DELETE FROM watches WHERE id = %s", (watch_id,))
        cur.close()
        conn.close()
        name = w["name"] if w else "Товар"
        await query.edit_message_text(f"🗑 {name} удалён")

    elif data.startswith("recheck_"):
        watch_id = int(data.split("_")[1])
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM watches WHERE id = %s", (watch_id,))
        w = cur.fetchone()
        cur.close()
        conn.close()
        if not w:
            await query.edit_message_text("❌ Товар не найден")
            return

        result = await scrape_price(w["url"], w["css_selector"])
        if result["price"] is not None:
            old_price = float(w["last_price"]) if w["last_price"] else None
            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute(
                "INSERT INTO price_history (watch_id, price, raw_text) VALUES (%s, %s, %s)",
                (watch_id, result["price"], result["raw_text"])
            )
            cur2.execute(
                "UPDATE watches SET last_price = %s, last_checked = NOW() WHERE id = %s",
                (result["price"], watch_id)
            )
            cur2.close()
            conn2.close()

            diff_str = ""
            if old_price and result["price"] != old_price:
                diff = result["price"] - old_price
                pct = (diff / old_price) * 100
                diff_str = f"\nИзменение: {diff:+.2f} ({pct:+.1f}%)"

            await query.edit_message_text(
                f"✅ {w['name']}: {result['price']:.2f} ₽{diff_str}",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(f"❌ Не удалось получить цену: {result.get('error', 'unknown')}")


# --- Scheduled Price Check ---

async def scheduled_check():
    """Called by scheduler to check all active watches."""
    logger.info("Scheduled price check starting...")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches WHERE is_active = true")
    watches = cur.fetchall()
    cur.close()
    conn.close()

    for w in watches:
        try:
            result = await scrape_price(w["url"], w["css_selector"])
            if result["price"] is None:
                continue

            old_price = float(w["last_price"]) if w["last_price"] else None

            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute(
                "INSERT INTO price_history (watch_id, price, raw_text) VALUES (%s, %s, %s)",
                (w["id"], result["price"], result["raw_text"])
            )
            cur2.execute(
                "UPDATE watches SET last_price = %s, last_checked = NOW() WHERE id = %s",
                (result["price"], w["id"])
            )
            cur2.close()
            conn2.close()

            # Check alerts
            await _check_and_alert(w, result["price"], old_price)

        except Exception as e:
            logger.error(f"Scheduled check error for {w['name']}: {e}")

    logger.info(f"Scheduled check done: {len(watches)} watches")


async def _check_and_alert(watch: dict, price: float, old_price: float | None):
    """Check thresholds and send alerts."""
    name = watch["name"]
    url = watch["url"]
    alert_sent = False

    # Price changed
    if old_price is not None and price != old_price:
        diff = price - old_price
        pct = (diff / old_price) * 100 if old_price else 0
        direction = "📈 Цена выросла" if diff > 0 else "📉 Цена снизилась"
        msg = (
            f"{direction}\n\n"
            f"📦 <b>{name}</b>\n"
            f"Было: {old_price:.2f} ₽\n"
            f"Стало: <b>{price:.2f} ₽</b>\n"
            f"Изменение: {diff:+.2f} ({pct:+.1f}%)\n"
            f"<a href='{url}'>Открыть</a>"
        )
        await send_notification(msg)
        alert_sent = True

    # Threshold below
    tb = watch.get("threshold_below")
    if tb and price <= float(tb):
        msg = (
            f"🔔 <b>Цена ниже порога!</b>\n\n"
            f"📦 {name}\n"
            f"💰 {price:.2f} ₽ (порог: {tb} ₽)\n"
            f"<a href='{url}'>Открыть</a>"
        )
        await send_notification(msg)
        alert_sent = True

    # Threshold above
    ta = watch.get("threshold_above")
    if ta and price >= float(ta):
        msg = (
            f"⚠️ <b>Цена выше порога!</b>\n\n"
            f"📦 {name}\n"
            f"💰 {price:.2f} ₽ (порог: {ta} ₽)\n"
            f"<a href='{url}'>Открыть</a>"
        )
        await send_notification(msg)
        alert_sent = True

    # Log alert
    if alert_sent:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO alerts_log (watch_id, alert_type, message, price) VALUES (%s, %s, %s, %s)",
            (watch["id"], "price_change", f"{old_price} -> {price}", price)
        )
        cur.close()
        conn.close()


def build_bot_app() -> Application:
    """Build and return the telegram bot application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation for adding watches
    conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_url)],
            SELECTOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_selector),
                CommandHandler("skip", add_selector),
            ],
            THRESHOLDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_thresholds),
                CommandHandler("skip", add_thresholds),
            ],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.Regex(r'^/detail_\d+'), cmd_detail))
    app.add_handler(CallbackQueryHandler(callback_handler))

    return app
