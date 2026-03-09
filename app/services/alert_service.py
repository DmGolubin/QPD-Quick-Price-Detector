"""Alert conditions evaluation, cooldown, compound conditions."""
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertCondition, AlertLog
from app.models.monitor import Monitor
from app.models.price import PriceHistory

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def evaluate_conditions(self, monitor: Monitor, old_price: float | None,
                                  new_price: float) -> list[dict]:
        alerts = []
        # Check explicit conditions
        result = await self.session.execute(
            select(AlertCondition).where(
                AlertCondition.monitor_id == monitor.id,
                AlertCondition.is_active == True,
                AlertCondition.parent_condition_id.is_(None),
            )
        )
        conditions = list(result.scalars().all())
        for cond in conditions:
            if await self._is_cooldown_active(cond):
                continue
            triggered = await self._evaluate_single(cond, old_price, new_price, monitor)
            if triggered:
                msg = triggered["message"]
                await self._log_alert(monitor, cond, msg, old_price, new_price)
                cond.last_triggered_at = datetime.now(timezone.utc)
                alerts.append(triggered)
        # Check threshold_below / threshold_above from monitor fields
        if old_price is not None:
            if monitor.threshold_below and new_price <= float(monitor.threshold_below):
                if old_price > float(monitor.threshold_below):
                    msg = f"📉 Цена ниже порога {monitor.threshold_below}: {new_price}"
                    alerts.append({"type": "threshold_below", "message": msg})
                    await self._log_alert_simple(monitor, "threshold_below", msg, old_price, new_price)
            if monitor.threshold_above and new_price >= float(monitor.threshold_above):
                if old_price < float(monitor.threshold_above):
                    msg = f"📈 Цена выше порога {monitor.threshold_above}: {new_price}"
                    alerts.append({"type": "threshold_above", "message": msg})
                    await self._log_alert_simple(monitor, "threshold_above", msg, old_price, new_price)
            if monitor.threshold_pct:
                pct = abs(new_price - old_price) / old_price * 100
                if pct >= float(monitor.threshold_pct):
                    direction = "📉" if new_price < old_price else "📈"
                    msg = f"{direction} Цена изменилась на {pct:.1f}%: {old_price} → {new_price}"
                    alerts.append({"type": "threshold_pct", "message": msg})
                    await self._log_alert_simple(monitor, "threshold_pct", msg, old_price, new_price)
        # Historical minimum check
        min_result = await self.session.execute(
            select(func.min(PriceHistory.price)).where(
                PriceHistory.monitor_id == monitor.id,
                PriceHistory.price.isnot(None),
            )
        )
        hist_min = min_result.scalar()
        if hist_min is not None and new_price <= float(hist_min):
            msg = f"🏆 Лучшая цена за всё время: {new_price}"
            alerts.append({"type": "historical_min", "message": msg})
            await self._log_alert_simple(monitor, "historical_min", msg, old_price, new_price)
        await self.session.commit()
        return alerts

    async def _evaluate_single(self, cond: AlertCondition, old_price: float | None,
                               new_price: float, monitor: Monitor) -> dict | None:
        if cond.type == "threshold_below" and cond.value:
            if new_price <= float(cond.value):
                return {"type": "threshold_below", "message": f"Цена ниже {cond.value}: {new_price}"}
        elif cond.type == "threshold_above" and cond.value:
            if new_price >= float(cond.value):
                return {"type": "threshold_above", "message": f"Цена выше {cond.value}: {new_price}"}
        elif cond.type == "threshold_pct" and cond.value and old_price:
            pct = abs(new_price - old_price) / old_price * 100
            if pct >= float(cond.value):
                return {"type": "threshold_pct", "message": f"Изменение {pct:.1f}%: {old_price} → {new_price}"}
        elif cond.type == "compound":
            return await self._evaluate_compound(cond, old_price, new_price, monitor)
        return None

    async def _evaluate_compound(self, cond: AlertCondition, old_price, new_price, monitor) -> dict | None:
        result = await self.session.execute(
            select(AlertCondition).where(AlertCondition.parent_condition_id == cond.id)
        )
        children = list(result.scalars().all())
        if not children:
            return None
        results = []
        for child in children:
            r = await self._evaluate_single(child, old_price, new_price, monitor)
            results.append(r is not None)
        if cond.operator == "AND" and all(results):
            return {"type": "compound_and", "message": f"Составное условие AND выполнено"}
        if cond.operator == "OR" and any(results):
            return {"type": "compound_or", "message": f"Составное условие OR выполнено"}
        return None

    async def _is_cooldown_active(self, cond: AlertCondition) -> bool:
        if not cond.last_triggered_at:
            return False
        cooldown = timedelta(seconds=cond.cooldown_seconds)
        return datetime.now(timezone.utc) - cond.last_triggered_at.replace(tzinfo=timezone.utc) < cooldown

    async def _log_alert(self, monitor, cond, message, old_price, new_price):
        change_pct = None
        if old_price and new_price and old_price != 0:
            change_pct = (new_price - old_price) / old_price * 100
        log = AlertLog(
            monitor_id=monitor.id, user_id=monitor.user_id, condition_id=cond.id,
            alert_type=cond.type, message=message,
            old_price=old_price, new_price=new_price, change_pct=change_pct,
        )
        self.session.add(log)

    async def _log_alert_simple(self, monitor, alert_type, message, old_price, new_price):
        change_pct = None
        if old_price and new_price and old_price != 0:
            change_pct = (new_price - old_price) / old_price * 100
        log = AlertLog(
            monitor_id=monitor.id, user_id=monitor.user_id,
            alert_type=alert_type, message=message,
            old_price=old_price, new_price=new_price, change_pct=change_pct,
        )
        self.session.add(log)
