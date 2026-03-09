"""Main API v1 router."""
from fastapi import APIRouter

from app.api.monitors import router as monitors_router
from app.api.history import router as history_router
from app.api.alerts import router as alerts_router
from app.api.groups import router as groups_router
from app.api.tags import router as tags_router
from app.api.export import router as export_router
from app.api.bulk import router as bulk_router
from app.api.templates import router as templates_router
from app.api.settings import router as settings_router
from app.api.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(monitors_router)
api_v1_router.include_router(history_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(groups_router)
api_v1_router.include_router(tags_router)
api_v1_router.include_router(export_router)
api_v1_router.include_router(bulk_router)
api_v1_router.include_router(templates_router)
api_v1_router.include_router(settings_router)
