"""Persistent responsibility, delivery review and issue handling."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, UUIDMixin


class TaskGovernance(Base, TimestampMixin):
    __tablename__ = "task_governance"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    acceptance_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    deliverable_url: Mapped[str | None] = mapped_column(Text)
    deliverable_note: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(32), default="not_submitted", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    handover_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskIssue(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_issues"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    reporter_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskChange(Base, UUIDMixin):
    __tablename__ = "task_changes"

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    before_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
