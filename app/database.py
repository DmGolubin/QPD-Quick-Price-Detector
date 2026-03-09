"""Async database connection with asyncpg + SQLAlchemy async."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

_db_url = settings.DATABASE_URL

if _db_url:
    if _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(
        _db_url,
        pool_size=20,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
    logger.warning("DATABASE_URL not set — database features disabled")
    engine = None
    async_session = None


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    if async_session is None:
        raise RuntimeError("Database not configured — set DATABASE_URL")
    async with async_session() as session:
        yield session
