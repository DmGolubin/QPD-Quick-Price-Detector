"""Playwright-based scraping engine with browser pool, retry, macros."""
import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.price_parser import PriceParser

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

AUTO_PRICE_SELECTORS = [
    "[data-price]", "[itemprop='price']", ".price", ".product-price",
    ".current-price", ".sale-price", ".Price", "#price", ".price-current",
    ".price__current", ".product__price", ".pdp-price", ".offer-price",
    "[class*='price']", "[class*='Price']", ".price-value",
    ".price_value", ".product-price-current", "span.price",
]

POPUP_SELECTORS = [
    "[class*='cookie'] button", "[class*='Cookie'] button",
    "[id*='cookie'] button", ".cookie-accept", "#cookie-accept",
    "[class*='consent'] button", "[class*='popup'] [class*='close']",
    "[class*='modal'] [class*='close']", "button[class*='close']",
    "[aria-label='Close']", "[aria-label='Закрыть']",
]


@dataclass
class ScrapeConfig:
    css_selector: str | None = None
    xpath_selector: str | None = None
    js_expression: str | None = None
    macro_steps: list[dict] = field(default_factory=list)
    proxy_url: str | None = None
    currency: str = "RUB"
    take_screenshot: bool = True


@dataclass
class ScrapeResult:
    price: float | None = None
    raw_text: str = ""
    title: str = ""
    screenshot: bytes | None = None
    availability_status: str | None = None
    error: str | None = None


class ScraperService:
    def __init__(self, max_browsers: int = 3, proxy_url: str | None = None):
        self.max_browsers = max_browsers
        self.default_proxy = proxy_url
        self._browser_pool: asyncio.Queue | None = None
        self._playwright = None
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser_pool = asyncio.Queue()
        for _ in range(self.max_browsers):
            browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            await self._browser_pool.put(browser)
        self._initialized = True

    async def shutdown(self):
        if not self._initialized:
            return
        while not self._browser_pool.empty():
            browser = await self._browser_pool.get()
            await browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False

    async def scrape(self, url: str, config: ScrapeConfig) -> ScrapeResult:
        if not self._initialized:
            await self.initialize()
        result = ScrapeResult()
        browser = await self._browser_pool.get()
        try:
            proxy = config.proxy_url or self.default_proxy
            ctx_opts = {"user_agent": random.choice(USER_AGENTS), "viewport": {"width": 1280, "height": 800}}
            if proxy:
                ctx_opts["proxy"] = {"server": proxy}
            context = await browser.new_context(**ctx_opts)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1)
                # Close popups
                await self._close_popups(page)
                # Execute macros
                if config.macro_steps:
                    await self._execute_macros(page, config.macro_steps)
                # Screenshot
                if config.take_screenshot:
                    try:
                        result.screenshot = await page.screenshot(type="jpeg", quality=80, full_page=False)
                    except Exception as e:
                        logger.warning(f"Screenshot failed: {e}")
                # Title
                result.title = await page.title() or ""
                # Extract price
                raw_text, price = await self._extract_price(page, config)
                result.raw_text = raw_text
                result.price = price
            finally:
                await context.close()
        except Exception as e:
            result.error = str(e)
            logger.error(f"Scrape error for {url}: {e}")
        finally:
            await self._browser_pool.put(browser)
        return result

    async def scrape_with_retry(self, url: str, config: ScrapeConfig, max_retries: int = 3) -> ScrapeResult:
        delays = [5, 15, 45]
        last_result = ScrapeResult(error="No attempts made")
        for attempt in range(max_retries):
            result = await self.scrape(url, config)
            if result.error is None:
                return result
            last_result = result
            if attempt < max_retries - 1:
                delay = delays[min(attempt, len(delays) - 1)]
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {url} in {delay}s: {result.error}")
                await asyncio.sleep(delay)
        return last_result

    async def _execute_macros(self, page, steps: list[dict]) -> None:
        for i, step in enumerate(steps[:20]):
            try:
                action = step.get("action_type", "")
                selector = step.get("selector", "")
                params = step.get("params", {})
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except json.JSONDecodeError:
                        params = {}
                if action == "click":
                    await page.click(selector, timeout=5000)
                elif action == "type":
                    await page.fill(selector, params.get("text", ""), timeout=5000)
                elif action == "scroll":
                    direction = params.get("direction", "down")
                    pixels = params.get("pixels", 500)
                    delta = pixels if direction == "down" else -pixels
                    await page.mouse.wheel(0, delta)
                elif action == "wait":
                    await asyncio.sleep(min(float(params.get("seconds", 1)), 10))
                elif action == "select_option":
                    await page.select_option(selector, params.get("value", ""), timeout=5000)
                elif action == "press_key":
                    await page.keyboard.press(params.get("key", "Enter"))
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"Macro step {i} ({step.get('action_type')}) failed: {e}")

    async def _close_popups(self, page) -> None:
        for sel in POPUP_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=500):
                    await el.click(timeout=1000)
                    await asyncio.sleep(0.3)
            except Exception:
                pass

    async def _extract_price(self, page, config: ScrapeConfig) -> tuple[str, float | None]:
        raw_text = ""
        # CSS selector
        if config.css_selector:
            try:
                el = page.locator(config.css_selector).first
                raw_text = (await el.text_content(timeout=5000)) or ""
                price = PriceParser.parse(raw_text, config.currency)
                if price is not None:
                    return raw_text, price
            except Exception as e:
                logger.debug(f"CSS selector failed: {e}")
        # XPath
        if config.xpath_selector:
            try:
                el = page.locator(f"xpath={config.xpath_selector}").first
                raw_text = (await el.text_content(timeout=5000)) or ""
                price = PriceParser.parse(raw_text, config.currency)
                if price is not None:
                    return raw_text, price
            except Exception as e:
                logger.debug(f"XPath selector failed: {e}")
        # JS expression
        if config.js_expression:
            try:
                raw_text = str(await page.evaluate(config.js_expression))
                price = PriceParser.parse(raw_text, config.currency)
                if price is not None:
                    return raw_text, price
            except Exception as e:
                logger.debug(f"JS expression failed: {e}")
        # Auto-detect
        for sel in AUTO_PRICE_SELECTORS:
            try:
                el = page.locator(sel).first
                text = (await el.text_content(timeout=2000)) or ""
                price = PriceParser.parse(text, config.currency)
                if price is not None and price > 0:
                    return text, price
            except Exception:
                continue
        return raw_text, None
