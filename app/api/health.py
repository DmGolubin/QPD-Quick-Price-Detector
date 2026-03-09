"""Health check endpoint."""
from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Always returns 200 so Railway keeps the container alive.
    Component statuses are informational only."""
    status = {"status": "ok", "components": {}}
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        status["components"]["database"] = "ok"
    except Exception as e:
        status["components"]["database"] = f"degraded: {str(e)}"
    return status
