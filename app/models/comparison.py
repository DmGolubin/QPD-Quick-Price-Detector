"""ComparisonGroup and ComparisonGroupMonitor models."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ComparisonGroup(Base):
    __tablename__ = "comparison_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    monitors = relationship("Monitor", secondary="comparison_group_monitors", backref="comparison_groups")


class ComparisonGroupMonitor(Base):
    __tablename__ = "comparison_group_monitors"

    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("comparison_groups.id", ondelete="CASCADE"), primary_key=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True)
