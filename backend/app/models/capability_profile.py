import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, Numeric, String, Text, Uuid, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from app.models import Base, TimestampMixin, UUIDMixin


class CapabilityProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "capability_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), unique=True, nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    performance_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="capability_profile")


class AIConfig(Base):
    __tablename__ = "ai_config"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="https://api.openai.com/v1")
    api_key_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o")
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    temperature: Mapped[Decimal] = mapped_column(Numeric(2, 1), default=Decimal("0.7"))
    # Custom system prompts (JSON text, overrides defaults in prompts.py)
    prompt_task_assign: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_capability: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_estimate: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_decompose: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
