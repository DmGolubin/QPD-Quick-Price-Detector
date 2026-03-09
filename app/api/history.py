"""Price history and chart API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.monitor_service import MonitorService

router = APIRouter(prefix="/monitors", tags=["history"], dependencies=[Depends(check_rate_limit)])


@router.get("/{monitor_id}/history")
async def get_history(monitor_id: int, days: int = 30, limit: int = 500,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    history = await ms.get_price_history(monitor_id, days, limit)
    return api_response(data=[{
        "id": h.id, "price": float(h.price) if h.price else None,
        "raw_text": h.raw_text, "availability_status": h.availability_status,
        "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None,
    } for h in history])


@router.get("/{monitor_id}/chart")
async def get_chart_data(monitor_id: int, days: int = 30,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    history = await ms.get_price_history(monitor_id, days, 2000)
    return api_response(data=[{
        "timestamp": h.recorded_at.isoformat() if h.recorded_at else None,
        "price": float(h.price) if h.price else None,
    } for h in reversed(history)])


@router.get("/{monitor_id}/stats")
async def get_stats(monitor_id: int, user=Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    stats = await ms.get_price_stats(monitor_id)
    return api_response(data=stats)
