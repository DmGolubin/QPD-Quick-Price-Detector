"""Bulk operations API endpoint."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.monitor_service import MonitorService

router = APIRouter(prefix="/monitors", tags=["bulk"], dependencies=[Depends(check_rate_limit)])


class BulkRequest(BaseModel):
    monitor_ids: list[int]
    operation: str  # pause, resume, delete, check_now, add_tag
    tag_name: Optional[str] = None


@router.post("/bulk")
async def bulk_operation(body: BulkRequest, user=Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    ms = MonitorService(session)
    result = await ms.bulk_operation(user.id, body.monitor_ids, body.operation, body.tag_name)
    return api_response(data=result)
