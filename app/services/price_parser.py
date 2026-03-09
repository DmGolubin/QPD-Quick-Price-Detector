"""Price parsing, formatting, and currency conversion."""
import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import aiohttp
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_exchange_cache = TTLCache(maxsize=100, ttl=21600)  # 6 hours


class PriceParser:
    CURRENCY_SYMBOLS = {
        "RUB": "₽", "USD": "$", "EUR": "€", "GBP": "£",
        "KZT": "₸", "CNY": "¥", "TRY": "₺",
    }
    SYMBOL_TO_CODE = {v: k for k, v in CURRENCY_SYMBOLS.items()}

    @staticmethod
    def parse(text: str, currency: str = "RUB") -> Optional[float]:
        if not text:
            return None
        cleaned = text.strip()
        # Remove currency symbols and text
        for sym in PriceParser.CURRENCY_SYMBOLS.values():
            cleaned = cleaned.replace(sym, "")
        for word in ["руб", "р.", "USD", "EUR", "GBP", "KZT", "CNY", "TRY", "RUB"]:
            cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)
        # Normalize whitespace
        cleaned = cleaned.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
        cleaned = cleaned.strip()
        if not cleaned:
            return None
        # Extract number-like pattern
        match = re.search(r"[\d\s.,]+\d", cleaned)
        if not match:
            # Try just digits
            match = re.search(r"\d+", cleaned)
            if not match:
                return None
            return float(match.group())
        num_str = match.group().strip()
        # Determine separators
        # Count dots and commas
        dots = num_str.count(".")
        commas = num_str.count(",")
        if dots == 0 and commas == 0:
            # Just digits and spaces: "1 299" -> 1299
            return float(num_str.replace(" ", ""))
        if dots == 1 and commas == 0:
            # "12.99" or "1.299" — check digits after dot
            parts = num_str.replace(" ", "").split(".")
            if len(parts[1]) == 3 and len(parts[0]) <= 3:
                # Likely thousands separator: "1.299" -> 1299
                return float(num_str.replace(" ", "").replace(".", ""))
            return float(num_str.replace(" ", ""))
        if commas == 1 and dots == 0:
            # "12,99" or "1,299"
            parts = num_str.replace(" ", "").split(",")
            if len(parts[1]) == 3 and len(parts[0]) <= 3:
                # Likely thousands: "1,299" -> 1299
                return float(num_str.replace(" ", "").replace(",", ""))
            # Decimal comma: "12,99" -> 12.99
            return float(num_str.replace(" ", "").replace(",", "."))
        if dots >= 1 and commas == 1:
            # "1.299,90" -> 1299.90
            return float(num_str.replace(" ", "").replace(".", "").replace(",", "."))
        if commas >= 1 and dots == 1:
            # "1,299.90" -> 1299.90
            return float(num_str.replace(" ", "").replace(",", ""))
        if dots > 1:
            # Multiple dots as thousands: "1.299.000" -> 1299000
            return float(num_str.replace(" ", "").replace(".", ""))
        if commas > 1:
            # Multiple commas as thousands: "1,299,000" -> 1299000
            return float(num_str.replace(" ", "").replace(",", ""))
        # Fallback
        try:
            return float(re.sub(r"[^\d.]", "", num_str))
        except ValueError:
            return None

    @staticmethod
    def format_price(value: float, currency: str = "RUB") -> str:
        sym = PriceParser.CURRENCY_SYMBOLS.get(currency, currency)
        if currency in ("USD", "GBP"):
            if value == int(value):
                return f"{sym}{int(value)}"
            return f"{sym}{value:,.2f}"
        if currency in ("EUR",):
            if value == int(value):
                return f"{int(value)} {sym}"
            formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
            return f"{formatted} {sym}"
        # RUB, KZT, CNY, TRY and others
        if value == int(value):
            formatted = f"{int(value):,}".replace(",", " ")
        else:
            formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return f"{formatted} {sym}"

    @staticmethod
    async def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return amount
        cache_key = f"{from_currency}_{to_currency}"
        if cache_key in _exchange_cache:
            return amount * _exchange_cache[cache_key]
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    rate = data["rates"].get(to_currency, 1.0)
                    _exchange_cache[cache_key] = rate
                    return amount * rate
        except Exception as e:
            logger.warning(f"Currency conversion failed: {e}")
            return amount
