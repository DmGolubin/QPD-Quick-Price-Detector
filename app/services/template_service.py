"""Monitor templates for popular stores."""
import json
import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import Monitor, MonitorTemplate

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATES = [
    {"domain": "ozon.ru", "store_name": "Ozon", "css_selector": "[data-widget='webPrice'] span.lp4_27", "currency": "RUB"},
    {"domain": "wildberries.ru", "store_name": "Wildberries", "css_selector": ".price-block__final-price, .product-page__price-block ins.price-block__final-price", "currency": "RUB"},
    {"domain": "market.yandex.ru", "store_name": "Яндекс.Маркет", "css_selector": "[data-auto='mainPrice'] span, .n-price-old__price", "currency": "RUB"},
    {"domain": "dns-shop.ru", "store_name": "DNS", "css_selector": ".product-buy__price, .current-price-value", "currency": "RUB"},
    {"domain": "mvideo.ru", "store_name": "М.Видео", "css_selector": ".price__main-value, .c-pdp-price__current", "currency": "RUB"},
    {"domain": "citilink.ru", "store_name": "Ситилинк", "css_selector": ".ProductHeader__price-default_current-price, .ProductCardVerticalLayout__price_current-price", "currency": "RUB"},
    {"domain": "aliexpress.com", "store_name": "AliExpress", "css_selector": ".product-price-current, .uniform-banner-box-price", "currency": "USD"},
    {"domain": "aliexpress.ru", "store_name": "AliExpress RU", "css_selector": ".product-price-current, .snow-price_SnowPrice__mainM", "currency": "RUB"},
    {"domain": "amazon.com", "store_name": "Amazon", "css_selector": ".a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice", "currency": "USD"},
    {"domain": "ebay.com", "store_name": "eBay", "css_selector": ".x-price-primary span, [itemprop='price']", "currency": "USD"},
    {"domain": "asos.com", "store_name": "ASOS", "css_selector": "[data-testid='current-price'], .product-price span", "currency": "GBP"},
    {"domain": "lamoda.ru", "store_name": "Lamoda", "css_selector": ".product-prices__price_new, .product-prices__price_single", "currency": "RUB"},
    {"domain": "avito.ru", "store_name": "Avito", "css_selector": "[itemprop='price'], .js-item-price", "currency": "RUB"},
    {"domain": "ikea.com", "store_name": "IKEA", "css_selector": ".pip-temp-price__integer, .pip-price__integer", "currency": "RUB"},
    {"domain": "leroymerlin.ru", "store_name": "Leroy Merlin", "css_selector": ".primary-price span, [slot='price']", "currency": "RUB"},
]


class TemplateService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed_templates(self):
        for t in SYSTEM_TEMPLATES:
            existing = await self.session.execute(
                select(MonitorTemplate).where(MonitorTemplate.domain == t["domain"])
            )
            if existing.scalar_one_or_none():
                continue
            template = MonitorTemplate(
                domain=t["domain"], store_name=t["store_name"],
                css_selector=t.get("css_selector"), currency=t.get("currency", "RUB"),
                is_system=True,
            )
            self.session.add(template)
        await self.session.commit()

    async def get_template_for_url(self, url: str) -> MonitorTemplate | None:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        result = await self.session.execute(
            select(MonitorTemplate).where(MonitorTemplate.domain == domain)
        )
        template = result.scalar_one_or_none()
        if template:
            return template
        # Try partial match
        for part in domain.split("."):
            result = await self.session.execute(
                select(MonitorTemplate).where(MonitorTemplate.domain.contains(part))
            )
            t = result.scalars().first()
            if t:
                return t
        return None

    async def apply_template(self, monitor: Monitor, template: MonitorTemplate):
        if not monitor.css_selector and template.css_selector:
            monitor.css_selector = template.css_selector
        if not monitor.xpath_selector and template.xpath_selector:
            monitor.xpath_selector = template.xpath_selector
        if template.currency:
            monitor.currency = template.currency
        if template.availability_patterns:
            monitor.availability_patterns = template.availability_patterns
        monitor.template_id = template.id

    async def list_templates(self) -> list[MonitorTemplate]:
        result = await self.session.execute(select(MonitorTemplate).order_by(MonitorTemplate.store_name))
        return list(result.scalars().all())
