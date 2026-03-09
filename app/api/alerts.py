"""Alerts API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.models.alert import AlertCondition, AlertLog

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(check_rate_limit)])


class AlertConditionCreate(BaseModel):
    monitor_id: int
    type: str
    value: Optional[float] = None
    operator: Optional[str] = None
    parent_condition_id: Optional[int] = None
    cooldown_seconds: int = 3600


@router.get("")
async def list_alerts(page: int = 1, per_page: int = 20, monitor_id: int = None,
                      alert_type: str = None,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    query = select(AlertLog).where(AlertLog.user_id == user.id)
    if monitor_id:
        query = query.where(AlertLog.monitor_id == monitor_id)
    if alert_type:
        query = query.where(AlertLog.alert_type == alert_type)
    query = query.order_by(AlertLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(query)
    alerts = list(result.scalars().all())
    return api_response(data=[{
        "id": a.id, "monitor_id": a.monitor_id, "alert_type": a.alert_type,
        "message": a.message,
        "old_price": float(a.old_price) if a.old_price else None,
        "new_price": float(a.new_price) if a.new_price else None,
        "change_pct": float(a.change_pct) if a.change_pct else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in alerts])


@router.get("/conditions/{monitor_id}")
async def get_conditions(monitor_id: int, user=Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AlertCondition).where(AlertCondition.monitor_id == monitor_id)
    )
    conditions = list(result.scalars().all())
    return api_response(data=[{
        "id": c.id, "type": c.type, "value": float(c.value) if c.value else None,
        "operator": c.operator, "cooldown_seconds": c.cooldown_seconds,
        "is_active": c.is_active,
    } for c in conditions])


@router.post("/conditions", status_code=201)
async def create_condition(body: AlertConditionCreate, user=Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    cond = AlertCondition(
        monitor_id=body.monitor_id, type=body.type, value=body.value,
        operator=body.operator, parent_condition_id=body.parent_condition_id,
        cooldown_seconds=body.cooldown_seconds,
    )
    session.add(cond)
    await session.commit()
    await session.refresh(cond)
    return api_response(data={"id": cond.id, "type": cond.type})
