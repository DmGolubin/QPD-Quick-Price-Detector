"""Import/export API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.export_service import ExportService

router = APIRouter(tags=["export"], dependencies=[Depends(check_rate_limit)])


@router.get("/export/json")
async def export_json(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    es = ExportService(session)
    data = await es.export_json(user.id)
    return api_response(data=data)


@router.get("/export/csv")
async def export_csv(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    es = ExportService(session)
    csv_data = await es.export_csv(user.id)
    return PlainTextResponse(csv_data, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=monitors.csv"})


@router.post("/import/json")
async def import_json(data: dict, user=Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    es = ExportService(session)
    result = await es.import_json(user.id, data)
    return api_response(data=result)
