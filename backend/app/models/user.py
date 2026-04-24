import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """Built-in roles (kept for reference, but role field is now free-form string)."""
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="member")
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    capability_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    performance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    assignments = relationship("Assignment", back_populates="user", cascade="all, delete-orphan")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    owned_projects = relationship("Project", back_populates="owner")
    skills = relationship("UserSkill", back_populates="user", cascade="all, delete-orphan")
    task_events = relationship("TaskEvent", back_populates="actor")
