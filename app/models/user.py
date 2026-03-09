"""User and APIKey models."""
from datetime import datetime, time
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    username: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    digest_frequency: Mapped[str] = mapped_column(String(20), default="none")
    digest_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    digest_day_of_week: Mapped[int] = mapped_column(Integer, default=1)
    default_check_interval: Mapped[int] = mapped_column(Integer, default=300)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    monitors = relationship("Monitor", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="api_keys")
