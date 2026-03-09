"""Digest and quiet hours service."""
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertLog, QueuedAlert
from app.models.monitor import Monitor
from app.models.price import PriceHistory
from app.models.user import User

logger = logging.getLogger(__name__)


class DigestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_quiet_hours(self, user_id: int) -> bool:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.quiet_hours_start or not user.quiet_hours_end:
            return False
        try:
            import pytz
            tz = pytz.timezone(user.timezone or "Europe/Moscow")
            now = datetime.now(tz).time()
        except Exception:
            now = datetime.now(timezone.utc).time()
        start, end = user.quiet_hours_start, user.quiet_hours_end
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end

    async def queue_alert(self, user_id: int, monitor_id: int, alert_type: str,
                          message: str, price: float | None = None):
        qa = QueuedAlert(
            user_id=user_id, monitor_id=monitor_id,
            alert_type=alert_type, message=message, price=price,
        )
        self.session.add(qa)
        await self.session.commit()

    async def send_queued_alerts(self, user_id: int) -> str | None:
        result = await self.session.execute(
            select(QueuedAlert).where(QueuedAlert.user_id == user_id).order_by(QueuedAlert.queued_at)
        )
        queued = list(result.scalars().all())
        if not queued:
            return None
        lines = ["📬 <b>Накопленные уведомления:</b>\n"]
        for qa in queued:
            lines.append(f"• {qa.message}")
        await self.session.execute(delete(QueuedAlert).where(QueuedAlert.user_id == user_id))
        await self.session.commit()
        return "\n".join(lines)

    async def generate_daily_digest(self, user_id: int) -> str:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.session.execute(
            select(AlertLog)
            .where(AlertLog.user_id == user_id, AlertLog.created_at >= since)
            .order_by(AlertLog.created_at.desc())
        )
        alerts = list(result.scalars().all())
        monitors_result = await self.session.execute(
            select(Monitor).where(Monitor.user_id == user_id, Monitor.is_active == True)
        )
        monitors = list(monitors_result.scalars().all())
        lines = [f"📊 <b>Ежедневный дайджест</b>\n"]
        lines.append(f"Активных мониторов: {len(monitors)}")
        lines.append(f"Алертов за 24ч: {len(alerts)}\n")
        for m in monitors[:20]:
            price_str = f"{float(m.last_price):.2f}" if m.last_price else "—"
            status = "✅" if m.is_active and (m.consecutive_failures or 0) == 0 else "⚠️"
            lines.append(f"{status} {m.name}: {price_str} {m.currency}")
        return "\n".join(lines)

    async def generate_weekly_digest(self, user_id: int) -> str:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        result = await self.session.execute(
            select(AlertLog)
            .where(AlertLog.user_id == user_id, AlertLog.created_at >= since)
            .order_by(AlertLog.created_at.desc())
        )
        alerts = list(result.scalars().all())
        lines = [f"📈 <b>Еженедельный дайджест</b>\n"]
        lines.append(f"Алертов за неделю: {len(alerts)}\n")
        if alerts:
            for a in alerts[:30]:
                lines.append(f"• {a.message}")
        return "\n".join(lines)
