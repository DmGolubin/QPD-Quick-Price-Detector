"""Health check endpoint."""
from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    status = {"status": "ok", "components": {}}
    # DB check
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        status["components"]["database"] = "ok"
    except Exception as e:
        status["components"]["database"] = f"error: {str(e)}"
        status["status"] = "degraded"
    return status
