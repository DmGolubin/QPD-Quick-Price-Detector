"""AlertCondition, AlertLog, NotificationChannel, QueuedAlert models."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AlertCondition(Base):
    __tablename__ = "alert_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    operator: Mapped[str | None] = mapped_column(String(5))
    parent_condition_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("alert_conditions.id", ondelete="CASCADE"))
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    monitor = relationship("Monitor", back_populates="alert_conditions")
    children = relationship("AlertCondition", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("AlertCondition", back_populates="children", remote_side="AlertCondition.id")


class AlertLog(Base):
    __tablename__ = "alerts_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    condition_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("alert_conditions.id", ondelete="SET NULL"))
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    monitor = relationship("Monitor", back_populates="alerts_log")


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    monitor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"))
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QueuedAlert(Base):
    __tablename__ = "queued_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    queued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
