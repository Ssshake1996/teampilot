"""Team planning facts: capacities, commitments and immutable planning/report snapshots."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, UUIDMixin


class WeekCapacity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "week_capacities"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    available_hours: Mapped[Decimal] = mapped_column(Numeric(7, 1), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class WeekAllocation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "week_allocations"
    __table_args__ = (UniqueConstraint("task_id", "user_id", "week_start"),)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(7, 1), nullable=False)


class ProjectMilestone(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_milestones"
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    task_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class TaskDependency(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id"),)
    predecessor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    successor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)


class PlanBaseline(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plan_baselines"
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)


class WeekCommitment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "week_commitments"
    __table_args__ = (UniqueConstraint("task_id", "week_start"),)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Retrospective(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "retrospectives"
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    decisions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action_task_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)


class ReportVersion(Base, UUIDMixin):
    __tablename__ = "report_versions"
    report_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audience_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True, index=True)
