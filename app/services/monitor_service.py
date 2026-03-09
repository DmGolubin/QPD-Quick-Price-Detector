"""Monitor CRUD, validation, duplicate detection, bulk operations."""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qs

from sqlalchemy import select, func, delete, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.monitor import Monitor
from app.models.price import PriceHistory
from app.models.tag import Tag, MonitorTag

logger = logging.getLogger(__name__)


class MonitorFilters:
    def __init__(self, tag: str | None = None, search: str | None = None,
                 status: str | None = None):
        self.tag = tag
        self.search = search
        self.status = status


class Pagination:
    def __init__(self, page: int = 1, per_page: int = 20):
        self.page = max(1, page)
        self.per_page = min(max(1, per_page), 100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class MonitorService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_monitor(self, user_id: int, data: dict) -> Monitor:
        url = data.get("url", "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("Невалидный URL: ожидается http:// или https://")
        normalized = self.normalize_url(url)
        if data.get("css_selector"):
            if not self.validate_css_selector(data["css_selector"]):
                raise ValueError("Невалидный CSS-селектор")
        interval = data.get("check_interval", 300)
        if not self.validate_check_interval(interval):
            raise ValueError("Интервал проверки должен быть от 60 секунд до 30 дней")
        monitor = Monitor(
            user_id=user_id,
            name=data.get("name", ""),
            url=url,
            normalized_url=normalized,
            css_selector=data.get("css_selector"),
            xpath_selector=data.get("xpath_selector"),
            js_expression=data.get("js_expression"),
            currency=data.get("currency", "RUB"),
            target_currency=data.get("target_currency"),
            threshold_below=data.get("threshold_below"),
            threshold_above=data.get("threshold_above"),
            threshold_pct=data.get("threshold_pct"),
            check_interval=interval,
            availability_selector=data.get("availability_selector"),
            availability_patterns=data.get("availability_patterns"),
        )
        self.session.add(monitor)
        await self.session.commit()
        await self.session.refresh(monitor)
        return monitor

    async def get_monitor(self, user_id: int, monitor_id: int) -> Monitor | None:
        result = await self.session.execute(
            select(Monitor).where(Monitor.id == monitor_id, Monitor.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_monitors(self, user_id: int, filters: MonitorFilters | None = None,
                            pagination: Pagination | None = None) -> dict:
        pagination = pagination or Pagination()
        query = select(Monitor).where(Monitor.user_id == user_id)
        count_query = select(func.count(Monitor.id)).where(Monitor.user_id == user_id)
        if filters:
            if filters.search:
                search = f"%{filters.search}%"
                query = query.where(Monitor.name.ilike(search) | Monitor.url.ilike(search))
                count_query = count_query.where(Monitor.name.ilike(search) | Monitor.url.ilike(search))
            if filters.status == "active":
                query = query.where(Monitor.is_active == True)
                count_query = count_query.where(Monitor.is_active == True)
            elif filters.status == "paused":
                query = query.where(Monitor.is_active == False)
                count_query = count_query.where(Monitor.is_active == False)
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0
        query = query.order_by(Monitor.created_at.desc())
        query = query.offset(pagination.offset).limit(pagination.per_page)
        result = await self.session.execute(query)
        monitors = list(result.scalars().all())
        return {
            "items": monitors,
            "total": total,
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total_pages": max(1, (total + pagination.per_page - 1) // pagination.per_page),
        }

    async def update_monitor(self, user_id: int, monitor_id: int, data: dict) -> Monitor | None:
        monitor = await self.get_monitor(user_id, monitor_id)
        if not monitor:
            return None
        if "css_selector" in data and data["css_selector"]:
            if not self.validate_css_selector(data["css_selector"]):
                raise ValueError("Невалидный CSS-селектор")
        if "check_interval" in data:
            if not self.validate_check_interval(data["check_interval"]):
                raise ValueError("Интервал проверки должен быть от 60 секунд до 30 дней")
        if "url" in data:
            data["normalized_url"] = self.normalize_url(data["url"])
        for key, value in data.items():
            if hasattr(monitor, key):
                setattr(monitor, key, value)
        monitor.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(monitor)
        return monitor

    async def delete_monitor(self, user_id: int, monitor_id: int) -> bool:
        monitor = await self.get_monitor(user_id, monitor_id)
        if not monitor:
            return False
        await self.session.delete(monitor)
        await self.session.commit()
        return True

    async def toggle_monitor(self, user_id: int, monitor_id: int) -> Monitor | None:
        monitor = await self.get_monitor(user_id, monitor_id)
        if not monitor:
            return None
        monitor.is_active = not monitor.is_active
        monitor.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(monitor)
        return monitor

    async def check_duplicate(self, user_id: int, url: str) -> Monitor | None:
        normalized = self.normalize_url(url)
        result = await self.session.execute(
            select(Monitor).where(
                Monitor.user_id == user_id,
                Monitor.normalized_url == normalized,
            )
        )
        return result.scalar_one_or_none()

    async def bulk_operation(self, user_id: int, monitor_ids: list[int], operation: str,
                             tag_name: str | None = None) -> dict:
        results = {"success": 0, "failed": 0}
        for mid in monitor_ids:
            monitor = await self.get_monitor(user_id, mid)
            if not monitor:
                results["failed"] += 1
                continue
            if operation == "pause":
                monitor.is_active = False
            elif operation == "resume":
                monitor.is_active = True
            elif operation == "delete":
                await self.session.delete(monitor)
            elif operation == "add_tag" and tag_name:
                pass  # handled separately
            results["success"] += 1
        await self.session.commit()
        return results

    async def get_stats(self, user_id: int) -> dict:
        total = await self.session.execute(
            select(func.count(Monitor.id)).where(Monitor.user_id == user_id)
        )
        active = await self.session.execute(
            select(func.count(Monitor.id)).where(Monitor.user_id == user_id, Monitor.is_active == True)
        )
        with_price = await self.session.execute(
            select(func.count(Monitor.id)).where(
                Monitor.user_id == user_id, Monitor.last_price.isnot(None)
            )
        )
        data_points = await self.session.execute(
            select(func.count(PriceHistory.id)).join(Monitor).where(Monitor.user_id == user_id)
        )
        return {
            "total_monitors": total.scalar() or 0,
            "active_monitors": active.scalar() or 0,
            "with_price": with_price.scalar() or 0,
            "data_points": data_points.scalar() or 0,
        }

    async def get_price_history(self, monitor_id: int, days: int = 30, limit: int = 1000) -> list:
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.session.execute(
            select(PriceHistory)
            .where(PriceHistory.monitor_id == monitor_id, PriceHistory.recorded_at >= since)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_price_stats(self, monitor_id: int) -> dict:
        result = await self.session.execute(
            select(
                func.min(PriceHistory.price),
                func.max(PriceHistory.price),
                func.avg(PriceHistory.price),
                func.count(PriceHistory.id),
            ).where(PriceHistory.monitor_id == monitor_id, PriceHistory.price.isnot(None))
        )
        row = result.one_or_none()
        if not row or not row[0]:
            return {"min": None, "max": None, "avg": None, "count": 0, "best_date": None}
        min_price_result = await self.session.execute(
            select(PriceHistory.recorded_at)
            .where(PriceHistory.monitor_id == monitor_id, PriceHistory.price == row[0])
            .order_by(PriceHistory.recorded_at.asc())
            .limit(1)
        )
        best_date = min_price_result.scalar_one_or_none()
        return {
            "min": float(row[0]) if row[0] else None,
            "max": float(row[1]) if row[1] else None,
            "avg": round(float(row[2]), 2) if row[2] else None,
            "count": row[3],
            "best_date": best_date.isoformat() if best_date else None,
        }

    @staticmethod
    def normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)
        sorted_params = urlencode(sorted(params.items()), doseq=True)
        return f"{scheme}://{netloc}{path}" + (f"?{sorted_params}" if sorted_params else "")

    @staticmethod
    def validate_css_selector(selector: str) -> bool:
        try:
            from cssselect import GenericTranslator
            GenericTranslator().css_to_xpath(selector)
            return True
        except Exception:
            return False

    @staticmethod
    def validate_check_interval(seconds: int) -> bool:
        return 60 <= seconds <= 2592000
