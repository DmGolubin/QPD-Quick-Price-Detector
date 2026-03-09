"""Tag and MonitorTag models."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    monitors = relationship("Monitor", secondary="monitor_tags", back_populates="tags")


class MonitorTag(Base):
    __tablename__ = "monitor_tags"

    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
