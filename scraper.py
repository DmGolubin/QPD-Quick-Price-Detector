import re
import logging
import asyncio
from playwright.async_api import async_playwright

logger = logging.getLogger("price-tracker.scraper")

_browser = None
_playwright = None


async def get_browser():
    """Lazy-init shared browser instance."""
    global _browser, _playwright
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--single-process",
            ]
        )
        logger.info("Browser launched")
    return _browser


async def close_browser():
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


def parse_price(text: str) -> float | None:
    """Extract numeric price from text like '1 299,90 ₽', '$12.99', '12 990₽'."""
    if not text:
        return None
    # Remove non-breaking spaces, thin spaces, etc.
    cleaned = text.replace('\xa0', ' ').replace('\u2009', ' ').strip()
    # Remove currency symbols and words
    cleaned = re.sub(r'[₽$€£¥₸руб\.рRUBUSDEURa-zA-Zа-яА-Я]', '', cleaned)
    cleaned = cleaned.strip()
    # Remove spaces used as thousand separators
    cleaned = re.sub(r'(\d)\s+(\d)', r'\1\2', cleaned)
    # Handle comma/dot decimal separators
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rindex(',') > cleaned.rindex('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')

    # Extract the number
    match = re.search(r'[\d]+(?:\.[\d]+)?', cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except (ValueError, TypeError):
        return None


async def scrape_price(url: str, css_selector: str | None = None) -> dict:
    """
    Scrape a page and extract price.
    Returns {"price": float|None, "raw_text": str, "title": str, "screenshot": bytes|None}
    """
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="ru-RU",
    )
    page = await context.new_page()

    result = {"price": None, "raw_text": "", "title": "", "screenshot": None, "error": None}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)  # Let JS render

        result["title"] = await page.title()

        if css_selector:
            try:
                el = await page.wait_for_selector(css_selector, timeout=10000)
                if el:
                    raw = await el.text_content()
                    result["raw_text"] = raw.strip() if raw else ""
                    result["price"] = parse_price(result["raw_text"])
            except Exception as e:
                logger.warning(f"Selector '{css_selector}' failed on {url}: {e}")
                result["error"] = f"Selector error: {e}"

        if result["price"] is None and not css_selector:
            # Auto-detect: try common price selectors
            for sel in _COMMON_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        raw = await el.text_content()
                        if raw:
                            price = parse_price(raw.strip())
                            if price and price > 0:
                                result["raw_text"] = raw.strip()
                                result["price"] = price
                                break
                except Exception:
                    continue

    except Exception as e:
        logger.error(f"Scrape error for {url}: {e}")
        result["error"] = str(e)
    finally:
        await context.close()

    return result


_COMMON_SELECTORS = [
    '[data-auto="price"] span',
    '[data-auto="price"]',
    '.price-value',
    '.product-price__value',
    '.price__current',
    'span[class*="price"]',
    'div[class*="price"]',
    '[itemprop="price"]',
    '.pdp-price',
    '.product-buy__price',
    'meta[itemprop="price"]',
]
