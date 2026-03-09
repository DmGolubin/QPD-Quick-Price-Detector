"""Web dashboard routes."""
import logging
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session, async_session
from app.services.auth_service import AuthService
from app.services.monitor_service import MonitorService, Pagination, MonitorFilters

logger = logging.getLogger(__name__)
router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="templates")


async def _get_web_user(request: Request, session: AsyncSession):
    token = request.cookies.get("session_token")
    if not token:
        return None
    auth = AuthService(session)
    user_id = auth.verify_session_token(token)
    if not user_id:
        return None
    return await auth.get_user_by_id(user_id)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, page: int = 1, search: str = None,
                    session: AsyncSession = Depends(get_session)):
    user = await _get_web_user(request, session)
    monitors = []
    stats = {"total_monitors": 0, "active_monitors": 0, "with_price": 0, "data_points": 0}
    total_pages = 1
    if user:
        ms = MonitorService(session)
        filters = MonitorFilters(search=search) if search else None
        result = await ms.list_monitors(user.id, filters, Pagination(page, 20))
        monitors = result["items"]
        total_pages = result["total_pages"]
        stats = await ms.get_stats(user.id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "monitors": monitors, "stats": stats,
        "page": page, "total_pages": total_pages, "search": search or "",
        "user": user,
    })


@router.get("/monitor/{monitor_id}", response_class=HTMLResponse)
async def monitor_detail(request: Request, monitor_id: int,
                         session: AsyncSession = Depends(get_session)):
    user = await _get_web_user(request, session)
    if not user:
        return RedirectResponse("/login")
    ms = MonitorService(session)
    monitor = await ms.get_monitor(user.id, monitor_id)
    if not monitor:
        return RedirectResponse("/")
    stats = await ms.get_price_stats(monitor_id)
    history = await ms.get_price_history(monitor_id, days=30, limit=200)
    return templates.TemplateResponse("detail.html", {
        "request": request, "monitor": monitor, "stats": stats,
        "history": history, "user": user,
    })


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, api_key: str = Form(...),
                       session: AsyncSession = Depends(get_session)):
    auth = AuthService(session)
    user = await auth.authenticate_api_key(api_key)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Неверный API-ключ",
        })
    token = auth.create_session_token(user.id)
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session_token", token, httponly=True, max_age=86400)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@router.post("/monitor/add")
async def add_monitor_web(request: Request, name: str = Form(...), url: str = Form(...),
                          css_selector: str = Form(""),
                          session: AsyncSession = Depends(get_session)):
    user = await _get_web_user(request, session)
    if not user:
        return RedirectResponse("/login")
    ms = MonitorService(session)
    try:
        await ms.create_monitor(user.id, {
            "name": name, "url": url,
            "css_selector": css_selector or None,
        })
    except ValueError:
        pass
    return RedirectResponse("/", status_code=302)
