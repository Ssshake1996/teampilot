import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin


class TaskStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.BACKLOG, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=True
    )
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assignee_id])
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    parent_task = relationship("Task", remote_side="Task.id", backref="subtasks")
    progress_logs = relationship("TaskProgress", back_populates="task", cascade="all, delete-orphan")
    required_skills = relationship("TaskRequiredSkill", back_populates="task", cascade="all, delete-orphan")


class TaskRequiredSkill(Base):
    __tablename__ = "task_required_skills"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id"), primary_key=True
    )
    min_proficiency: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    task = relationship("Task", back_populates="required_skills")
    skill = relationship("Skill")
