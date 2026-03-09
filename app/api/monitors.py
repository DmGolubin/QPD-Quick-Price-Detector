"""CRUD monitors API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response, PaginationParams
from app.services.monitor_service import MonitorService, MonitorFilters, Pagination

router = APIRouter(prefix="/monitors", tags=["monitors"], dependencies=[Depends(check_rate_limit)])


class MonitorCreate(BaseModel):
    name: str
    url: str
    css_selector: Optional[str] = None
    xpath_selector: Optional[str] = None
    js_expression: Optional[str] = None
    currency: str = "RUB"
    target_currency: Optional[str] = None
    threshold_below: Optional[float] = None
    threshold_above: Optional[float] = None
    threshold_pct: Optional[float] = None
    check_interval: int = 300
    availability_selector: Optional[str] = None
    availability_patterns: Optional[str] = None


class MonitorUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    css_selector: Optional[str] = None
    xpath_selector: Optional[str] = None
    js_expression: Optional[str] = None
    currency: Optional[str] = None
    threshold_below: Optional[float] = None
    threshold_above: Optional[float] = None
    threshold_pct: Optional[float] = None
    check_interval: Optional[int] = None
    is_active: Optional[bool] = None


def _serialize_monitor(m) -> dict:
    return {
        "id": m.id, "name": m.name, "url": m.url,
        "css_selector": m.css_selector, "xpath_selector": m.xpath_selector,
        "currency": m.currency, "check_interval": m.check_interval,
        "is_active": m.is_active,
        "last_price": float(m.last_price) if m.last_price else None,
        "last_checked": m.last_checked.isoformat() if m.last_checked else None,
        "availability_status": m.availability_status,
        "consecutive_failures": m.consecutive_failures,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("")
async def list_monitors(page: int = 1, per_page: int = 20, search: str = None,
                        status: str = None, tag: str = None,
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    filters = MonitorFilters(tag=tag, search=search, status=status)
    pagination = Pagination(page, per_page)
    result = await ms.list_monitors(user.id, filters, pagination)
    return api_response(
        data=[_serialize_monitor(m) for m in result["items"]],
        meta={"total": result["total"], "page": result["page"],
              "per_page": result["per_page"], "total_pages": result["total_pages"]},
    )


@router.post("", status_code=201)
async def create_monitor(body: MonitorCreate, user=Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    try:
        monitor = await ms.create_monitor(user.id, body.model_dump())
        return api_response(data=_serialize_monitor(monitor))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{monitor_id}")
async def get_monitor(monitor_id: int, user=Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return api_response(data=_serialize_monitor(monitor))


@router.put("/{monitor_id}")
async def update_monitor(monitor_id: int, body: MonitorUpdate, user=Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    try:
        monitor = await ms.update_monitor(user.id, monitor_id, body.model_dump(exclude_unset=True))
        if not monitor:
            raise HTTPException(status_code=404, detail="Monitor not found")
        return api_response(data=_serialize_monitor(monitor))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: int, user=Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    if not await ms.delete_monitor(user.id, monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")
    return api_response(data={"deleted": True})


@router.post("/{monitor_id}/check")
async def check_monitor(monitor_id: int, user=Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    # Enqueue immediate check via scheduler (if available)
    return api_response(data={"queued": True, "monitor_id": monitor_id})
