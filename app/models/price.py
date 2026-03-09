"""PriceHistory and Screenshot models."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    monitor = relationship("Monitor", back_populates="screenshots")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    raw_text: Mapped[str | None] = mapped_column(Text)
    availability_status: Mapped[str | None] = mapped_column(String(20))
    screenshot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("screenshots.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    monitor = relationship("Monitor", back_populates="price_history")
