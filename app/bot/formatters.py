"""Telegram message formatting utilities."""
from app.services.price_parser import PriceParser


def format_monitor_card(m, stats=None) -> str:
    status = "✅" if m.is_active else "⏸"
    if (m.consecutive_failures or 0) > 0:
        status = "⚠️"
    price_str = PriceParser.format_price(float(m.last_price), m.currency) if m.last_price else "—"
    avail = ""
    if m.availability_status == "out_of_stock":
        avail = " 🔴 Нет в наличии"
    elif m.availability_status == "in_stock":
        avail = " 🟢"
    lines = [
        f"{status} <b>{m.name}</b>",
        f"💰 {price_str}{avail}",
        f"🔗 <a href='{m.url}'>Ссылка</a>",
    ]
    if m.last_checked:
        lines.append(f"🕐 {m.last_checked.strftime('%d.%m %H:%M')}")
    if stats:
        if stats.get("min") is not None:
            lines.append(f"📊 Мин: {stats['min']} | Макс: {stats['max']} | Сред: {stats['avg']}")
    return "\n".join(lines)


def format_alert_message(monitor_name: str, alert_type: str, old_price, new_price,
                         currency: str, url: str) -> str:
    if old_price and new_price:
        change = new_price - old_price
        pct = (change / old_price * 100) if old_price else 0
        direction = "📉" if change < 0 else "📈"
        old_str = PriceParser.format_price(float(old_price), currency)
        new_str = PriceParser.format_price(float(new_price), currency)
        return (
            f"{direction} <b>{monitor_name}</b>\n"
            f"Было: {old_str}\n"
            f"Стало: {new_str} ({pct:+.1f}%)\n"
            f"<a href='{url}'>Открыть</a>"
        )
    return f"🔔 <b>{monitor_name}</b>\n{alert_type}\n<a href='{url}'>Открыть</a>"


def format_comparison_table(group_name: str, monitors: list) -> str:
    lines = [f"📊 <b>Сравнение: {group_name}</b>\n"]
    for i, m in enumerate(monitors, 1):
        price_str = PriceParser.format_price(float(m.last_price), m.currency) if m.last_price else "—"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        lines.append(f"{medal} {price_str} — {m.name}")
    return "\n".join(lines)


def parse_macro_text(text: str) -> list[dict]:
    """Parse macro from text format: 'click .btn; wait 2; scroll down 500'"""
    steps = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        tokens = part.split(None, 2)
        if not tokens:
            continue
        action = tokens[0].lower()
        if action == "click" and len(tokens) >= 2:
            steps.append({"action_type": "click", "selector": tokens[1], "params": "{}"})
        elif action == "type" and len(tokens) >= 3:
            steps.append({"action_type": "type", "selector": tokens[1], "params": f'{{"text": "{tokens[2]}"}}'})
        elif action == "scroll" and len(tokens) >= 3:
            steps.append({"action_type": "scroll", "selector": "", "params": f'{{"direction": "{tokens[1]}", "pixels": {tokens[2]}}}'})
        elif action == "wait" and len(tokens) >= 2:
            steps.append({"action_type": "wait", "selector": "", "params": f'{{"seconds": {tokens[1]}}}'})
        elif action == "select" and len(tokens) >= 3:
            steps.append({"action_type": "select_option", "selector": tokens[1], "params": f'{{"value": "{tokens[2]}"}}'})
        elif action == "press" and len(tokens) >= 2:
            steps.append({"action_type": "press_key", "selector": "", "params": f'{{"key": "{tokens[1]}"}}'})
    return steps
