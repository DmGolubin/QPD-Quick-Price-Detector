"""User settings and stats API endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.monitor_service import MonitorService

router = APIRouter(tags=["settings"], dependencies=[Depends(check_rate_limit)])


class SettingsUpdate(BaseModel):
    timezone: Optional[str] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    digest_frequency: Optional[str] = None
    default_check_interval: Optional[int] = None


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    return api_response(data={
        "timezone": user.timezone,
        "quiet_hours_start": str(user.quiet_hours_start) if user.quiet_hours_start else None,
        "quiet_hours_end": str(user.quiet_hours_end) if user.quiet_hours_end else None,
        "digest_frequency": user.digest_frequency,
        "default_check_interval": user.default_check_interval,
    })


@router.put("/settings")
async def update_settings(body: SettingsUpdate, user=Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    for key, value in body.model_dump(exclude_unset=True).items():
        if hasattr(user, key) and value is not None:
            setattr(user, key, value)
    await session.commit()
    return api_response(data={"updated": True})


@router.get("/stats")
async def get_stats(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    stats = await ms.get_stats(user.id)
    return api_response(data=stats)
