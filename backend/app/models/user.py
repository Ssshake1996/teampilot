import enum

from sqlalchemy import Boolean, String, Text
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

    # Relationships
    assigned_tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    owned_projects = relationship("Project", back_populates="owner")
    skills = relationship("UserSkill", back_populates="user", cascade="all, delete-orphan")
    capability_profile = relationship("CapabilityProfile", back_populates="user", uselist=False)
    progress_logs = relationship("TaskProgress", back_populates="user")
    project_memberships = relationship("ProjectMember", back_populates="user")
