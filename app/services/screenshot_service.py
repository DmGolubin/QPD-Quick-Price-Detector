"""Screenshot capture, storage, and rotation."""
import logging
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.price import Screenshot

logger = logging.getLogger(__name__)
MAX_SCREENSHOTS = 50


class ScreenshotService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_screenshot(self, monitor_id: int, image_data: bytes) -> Screenshot:
        ss = Screenshot(monitor_id=monitor_id, image_data=image_data)
        self.session.add(ss)
        await self.session.commit()
        await self.session.refresh(ss)
        await self._rotate(monitor_id)
        return ss

    async def get_screenshots(self, monitor_id: int, limit: int = 20) -> list[Screenshot]:
        result = await self.session.execute(
            select(Screenshot)
            .where(Screenshot.monitor_id == monitor_id)
            .order_by(Screenshot.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _rotate(self, monitor_id: int):
        count_result = await self.session.execute(
            select(func.count(Screenshot.id)).where(Screenshot.monitor_id == monitor_id)
        )
        count = count_result.scalar() or 0
        if count <= MAX_SCREENSHOTS:
            return
        excess = count - MAX_SCREENSHOTS
        oldest = await self.session.execute(
            select(Screenshot.id)
            .where(Screenshot.monitor_id == monitor_id)
            .order_by(Screenshot.created_at.asc())
            .limit(excess)
        )
        ids = [r for r in oldest.scalars().all()]
        if ids:
            await self.session.execute(delete(Screenshot).where(Screenshot.id.in_(ids)))
            await self.session.commit()
