"""Tags API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.models.tag import Tag, MonitorTag

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(check_rate_limit)])


class TagCreate(BaseModel):
    name: str


@router.get("")
async def list_tags(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).where(Tag.user_id == user.id))
    tags = list(result.scalars().all())
    return api_response(data=[{"id": t.id, "name": t.name} for t in tags])


@router.post("", status_code=201)
async def create_tag(body: TagCreate, user=Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    tag = Tag(user_id=user.id, name=body.name)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return api_response(data={"id": tag.id, "name": tag.name})


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, user=Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await session.execute(delete(MonitorTag).where(MonitorTag.tag_id == tag_id))
    await session.delete(tag)
    await session.commit()
    return api_response(data={"deleted": True})
