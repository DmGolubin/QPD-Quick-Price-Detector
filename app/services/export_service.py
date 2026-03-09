"""JSON/CSV export and import service."""
import csv
import io
import json
import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import Monitor
from app.models.price import PriceHistory

logger = logging.getLogger(__name__)


class ExportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def export_json(self, user_id: int) -> dict:
        result = await self.session.execute(
            select(Monitor).where(Monitor.user_id == user_id)
        )
        monitors = list(result.scalars().all())
        data = {"version": "1.0", "exported_at": datetime.utcnow().isoformat(), "monitors": []}
        for m in monitors:
            data["monitors"].append({
                "name": m.name, "url": m.url,
                "css_selector": m.css_selector, "xpath_selector": m.xpath_selector,
                "js_expression": m.js_expression, "currency": m.currency,
                "target_currency": m.target_currency,
                "threshold_below": float(m.threshold_below) if m.threshold_below else None,
                "threshold_above": float(m.threshold_above) if m.threshold_above else None,
                "threshold_pct": float(m.threshold_pct) if m.threshold_pct else None,
                "check_interval": m.check_interval, "is_active": m.is_active,
                "availability_selector": m.availability_selector,
                "availability_patterns": m.availability_patterns,
            })
        return data

    async def export_csv(self, user_id: int) -> str:
        result = await self.session.execute(
            select(Monitor).where(Monitor.user_id == user_id)
        )
        monitors = list(result.scalars().all())
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["name", "url", "current_price", "min_price", "max_price", "avg_price", "currency", "created_at"])
        for m in monitors:
            stats = await self.session.execute(
                select(
                    func.min(PriceHistory.price),
                    func.max(PriceHistory.price),
                    func.avg(PriceHistory.price),
                ).where(PriceHistory.monitor_id == m.id, PriceHistory.price.isnot(None))
            )
            row = stats.one()
            writer.writerow([
                m.name, m.url, float(m.last_price) if m.last_price else "",
                float(row[0]) if row[0] else "", float(row[1]) if row[1] else "",
                round(float(row[2]), 2) if row[2] else "",
                m.currency, m.created_at.isoformat() if m.created_at else "",
            ])
        return output.getvalue()

    async def import_json(self, user_id: int, data: dict) -> dict:
        from app.services.monitor_service import MonitorService
        ms = MonitorService(self.session)
        imported, skipped, errors = 0, 0, []
        monitors = data.get("monitors", [])
        for item in monitors:
            try:
                if not item.get("url"):
                    skipped += 1
                    errors.append(f"Missing URL: {item.get('name', 'unknown')}")
                    continue
                await ms.create_monitor(user_id, item)
                imported += 1
            except Exception as e:
                skipped += 1
                errors.append(f"{item.get('name', 'unknown')}: {str(e)}")
        return {"imported": imported, "skipped": skipped, "errors": errors}
