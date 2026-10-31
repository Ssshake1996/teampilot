import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin


class TaskEventType(str, enum.Enum):
    PROGRESS = "progress"
    SIGNOFF = "signoff"
    DELETE = "delete"
    RESTORE = "restore"
    REOPEN = "reopen"


class TaskEvent(Base, UUIDMixin):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_latest_progress", "task_id", "event_type", "created_at", "id"),)

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    event_type: Mapped[TaskEventType] = mapped_column(Enum(TaskEventType), nullable=False, index=True)
    progress_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours_spent: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    task = relationship("Task", back_populates="events")
    actor = relationship("User", back_populates="task_events")
