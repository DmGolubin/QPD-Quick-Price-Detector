"""Availability monitoring service."""
import json
import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_OOS_PATTERNS = [
    "out of stock", "нет в наличии", "sold out", "распродано",
    "товар закончился", "нет в продаже", "temporarily unavailable",
    "currently unavailable", "not available",
]


class AvailabilityService:
    @staticmethod
    async def check_availability(page, monitor) -> str | None:
        """Returns 'in_stock', 'out_of_stock', or None."""
        patterns = DEFAULT_OOS_PATTERNS
        if monitor.availability_patterns:
            try:
                custom = json.loads(monitor.availability_patterns)
                if isinstance(custom, list):
                    patterns = patterns + custom
            except json.JSONDecodeError:
                pass
        # Check custom selector first
        if monitor.availability_selector:
            try:
                el = page.locator(monitor.availability_selector).first
                text = (await el.text_content(timeout=3000)) or ""
                for pat in patterns:
                    if pat.lower() in text.lower():
                        return "out_of_stock"
                return "in_stock"
            except Exception:
                pass
        # Check full page text
        try:
            body_text = await page.inner_text("body", timeout=5000)
            body_lower = body_text.lower()
            for pat in patterns:
                if pat.lower() in body_lower:
                    return "out_of_stock"
            return "in_stock"
        except Exception as e:
            logger.debug(f"Availability check failed: {e}")
            return None
