"""Visual element selector service — server-side proxy for iframe."""
import logging
import random
import re
from urllib.parse import urljoin, urlparse

from app.services.scraper_service import USER_AGENTS

logger = logging.getLogger(__name__)

SELECTOR_JS = """
(function() {
    let selected = null;
    document.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (selected) selected.style.outline = '';
        selected = e.target;
        selected.style.outline = '3px solid #6c5ce7';
        const cssSelector = generateCSSSelector(selected);
        const xpath = generateXPath(selected);
        window.parent.postMessage({
            type: 'element_selected',
            css: cssSelector,
            xpath: xpath,
            text: selected.textContent.trim().substring(0, 500),
            tag: selected.tagName.toLowerCase(),
        }, '*');
    }, true);

    function generateCSSSelector(el) {
        if (el.id) return '#' + el.id;
        let path = [];
        while (el && el.nodeType === 1) {
            let selector = el.tagName.toLowerCase();
            if (el.id) { path.unshift('#' + el.id); break; }
            if (el.className && typeof el.className === 'string') {
                const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':'));
                if (classes.length) selector += '.' + classes.slice(0, 2).join('.');
            }
            let sibling = el, nth = 1;
            while (sibling = sibling.previousElementSibling) {
                if (sibling.tagName === el.tagName) nth++;
            }
            if (nth > 1) selector += ':nth-of-type(' + nth + ')';
            path.unshift(selector);
            el = el.parentElement;
        }
        return path.join(' > ');
    }

    function generateXPath(el) {
        let path = [];
        while (el && el.nodeType === 1) {
            let idx = 0, sibling = el;
            while (sibling) { if (sibling.tagName === el.tagName) idx++; sibling = sibling.previousElementSibling; }
            path.unshift(el.tagName.toLowerCase() + '[' + idx + ']');
            el = el.parentElement;
        }
        return '/' + path.join('/');
    }
})();
"""


class VisualSelectorService:
    def __init__(self, scraper):
        self.scraper = scraper

    async def proxy_page(self, url: str) -> str:
        if not self.scraper._initialized:
            await self.scraper.initialize()
        browser = await self.scraper._browser_pool.get()
        try:
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 900},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                java_script_enabled=True,
            )
            # Stealth: mask webdriver detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = {runtime: {}};
            """)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=45000)
                html = await page.content()
                # Rewrite relative URLs
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                html = re.sub(
                    r'(href|src|action)="(/[^"]*)"',
                    lambda m: f'{m.group(1)}="{urljoin(base_url, m.group(2))}"',
                    html,
                )
                # Inject selector JS
                inject = f"<script>{SELECTOR_JS}</script>"
                html = html.replace("</body>", f"{inject}</body>")
                return html
            finally:
                await context.close()
        finally:
            await self.scraper._browser_pool.put(browser)
