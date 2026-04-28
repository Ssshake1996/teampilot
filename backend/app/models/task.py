import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin


class TaskStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
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
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.NOT_STARTED, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    creator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=True
    )
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_off_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    required_skills_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    assignments = relationship("Assignment", back_populates="task", cascade="all, delete-orphan")
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    signed_off_by = relationship("User", foreign_keys=[signed_off_by_id])
    parent_task = relationship("Task", remote_side="Task.id", backref="subtasks")
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")
    data_skills = relationship("TaskDataSkill", back_populates="task", cascade="all, delete-orphan")
    skill_runs = relationship("SkillRun", back_populates="task", cascade="all, delete-orphan")
