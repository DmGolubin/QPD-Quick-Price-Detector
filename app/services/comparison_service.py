"""Comparison groups service."""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.comparison import ComparisonGroup, ComparisonGroupMonitor
from app.models.monitor import Monitor


class ComparisonService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_group(self, user_id: int, name: str, monitor_ids: list[int]) -> ComparisonGroup:
        group = ComparisonGroup(user_id=user_id, name=name)
        self.session.add(group)
        await self.session.flush()
        for mid in monitor_ids:
            self.session.add(ComparisonGroupMonitor(group_id=group.id, monitor_id=mid))
        await self.session.commit()
        await self.session.refresh(group)
        return group

    async def get_group(self, user_id: int, group_id: int) -> dict | None:
        result = await self.session.execute(
            select(ComparisonGroup).where(ComparisonGroup.id == group_id, ComparisonGroup.user_id == user_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            return None
        monitors_result = await self.session.execute(
            select(Monitor)
            .join(ComparisonGroupMonitor, Monitor.id == ComparisonGroupMonitor.monitor_id)
            .where(ComparisonGroupMonitor.group_id == group_id)
            .order_by(Monitor.last_price.asc().nullslast())
        )
        monitors = list(monitors_result.scalars().all())
        return {"group": group, "monitors": monitors}

    async def list_groups(self, user_id: int) -> list[ComparisonGroup]:
        result = await self.session.execute(
            select(ComparisonGroup).where(ComparisonGroup.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update_group(self, user_id: int, group_id: int, data: dict) -> ComparisonGroup | None:
        result = await self.session.execute(
            select(ComparisonGroup).where(ComparisonGroup.id == group_id, ComparisonGroup.user_id == user_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            return None
        if "name" in data:
            group.name = data["name"]
        if "monitor_ids" in data:
            await self.session.execute(
                delete(ComparisonGroupMonitor).where(ComparisonGroupMonitor.group_id == group_id)
            )
            for mid in data["monitor_ids"]:
                self.session.add(ComparisonGroupMonitor(group_id=group_id, monitor_id=mid))
        await self.session.commit()
        return group

    async def delete_group(self, user_id: int, group_id: int) -> bool:
        result = await self.session.execute(
            select(ComparisonGroup).where(ComparisonGroup.id == group_id, ComparisonGroup.user_id == user_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            return False
        await self.session.delete(group)
        await self.session.commit()
        return True
