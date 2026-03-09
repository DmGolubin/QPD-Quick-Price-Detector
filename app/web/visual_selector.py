"""Visual selector web routes."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session

router = APIRouter(prefix="/selector", tags=["visual_selector"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def visual_selector_page(request: Request, url: str = ""):
    return templates.TemplateResponse("visual_selector.html", {
        "request": request, "target_url": url,
    })


@router.post("/proxy")
async def proxy_page(request: Request):
    body = await request.json()
    url = body.get("url", "")
    if not url:
        return {"error": "URL required"}
    # Import here to avoid circular imports
    from app.services.scraper_service import ScraperService
    from app.services.visual_selector_service import VisualSelectorService
    scraper = ScraperService(max_browsers=1)
    vs = VisualSelectorService(scraper)
    try:
        html = await vs.proxy_page(url)
        return {"html": html}
    except Exception as e:
        return {"error": str(e)}
    finally:
        await scraper.shutdown()
