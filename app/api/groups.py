"""Comparison groups API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.comparison_service import ComparisonService

router = APIRouter(prefix="/groups", tags=["groups"], dependencies=[Depends(check_rate_limit)])


class GroupCreate(BaseModel):
    name: str
    monitor_ids: list[int] = []


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    monitor_ids: Optional[list[int]] = None


@router.get("")
async def list_groups(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    cs = ComparisonService(session)
    groups = await cs.list_groups(user.id)
    return api_response(data=[{"id": g.id, "name": g.name} for g in groups])


@router.post("", status_code=201)
async def create_group(body: GroupCreate, user=Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    cs = ComparisonService(session)
    group = await cs.create_group(user.id, body.name, body.monitor_ids)
    return api_response(data={"id": group.id, "name": group.name})


@router.get("/{group_id}")
async def get_group(group_id: int, user=Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    cs = ComparisonService(session)
    result = await cs.get_group(user.id, group_id)
    if not result:
        raise HTTPException(status_code=404, detail="Group not found")
    monitors = [{
        "id": m.id, "name": m.name, "url": m.url,
        "last_price": float(m.last_price) if m.last_price else None,
        "currency": m.currency,
    } for m in result["monitors"]]
    return api_response(data={"id": result["group"].id, "name": result["group"].name, "monitors": monitors})


@router.put("/{group_id}")
async def update_group(group_id: int, body: GroupUpdate, user=Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    cs = ComparisonService(session)
    group = await cs.update_group(user.id, group_id, body.model_dump(exclude_unset=True))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return api_response(data={"id": group.id, "name": group.name})


@router.delete("/{group_id}")
async def delete_group(group_id: int, user=Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    cs = ComparisonService(session)
    if not await cs.delete_group(user.id, group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    return api_response(data={"deleted": True})
