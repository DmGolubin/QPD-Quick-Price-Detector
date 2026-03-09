"""Monitor and MonitorTemplate models."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str | None] = mapped_column(Text)
    css_selector: Mapped[str | None] = mapped_column(String(500))
    xpath_selector: Mapped[str | None] = mapped_column(String(500))
    js_expression: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    target_currency: Mapped[str | None] = mapped_column(String(10))
    threshold_below: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    threshold_above: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    threshold_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    check_interval: Mapped[int] = mapped_column(Integer, default=300)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_raw_text: Mapped[str | None] = mapped_column(Text)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime)
    availability_status: Mapped[str | None] = mapped_column(String(20))
    availability_selector: Mapped[str | None] = mapped_column(String(500))
    availability_patterns: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="monitors")
    price_history = relationship("PriceHistory", back_populates="monitor", cascade="all, delete-orphan")
    screenshots = relationship("Screenshot", back_populates="monitor", cascade="all, delete-orphan")
    alert_conditions = relationship("AlertCondition", back_populates="monitor", cascade="all, delete-orphan")
    alerts_log = relationship("AlertLog", back_populates="monitor", cascade="all, delete-orphan")
    macros = relationship("Macro", back_populates="monitor", cascade="all, delete-orphan", order_by="Macro.step_order")
    tags = relationship("Tag", secondary="monitor_tags", back_populates="monitors")


class MonitorTemplate(Base):
    __tablename__ = "monitor_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    css_selector: Mapped[str | None] = mapped_column(String(500))
    xpath_selector: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    availability_patterns: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
