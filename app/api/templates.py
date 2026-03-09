"""Monitor templates API endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.api.deps import get_current_user, check_rate_limit, api_response
from app.services.template_service import TemplateService
from app.models.monitor import MonitorTemplate

router = APIRouter(prefix="/templates", tags=["templates"], dependencies=[Depends(check_rate_limit)])


class TemplateCreate(BaseModel):
    domain: str
    store_name: str
    css_selector: Optional[str] = None
    xpath_selector: Optional[str] = None
    currency: str = "RUB"


@router.get("")
async def list_templates(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ts = TemplateService(session)
    templates = await ts.list_templates()
    return api_response(data=[{
        "id": t.id, "domain": t.domain, "store_name": t.store_name,
        "css_selector": t.css_selector, "currency": t.currency, "is_system": t.is_system,
    } for t in templates])


@router.post("", status_code=201)
async def create_template(body: TemplateCreate, user=Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    template = MonitorTemplate(
        domain=body.domain, store_name=body.store_name,
        css_selector=body.css_selector, xpath_selector=body.xpath_selector,
        currency=body.currency, created_by=user.id,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return api_response(data={"id": template.id, "domain": template.domain})
