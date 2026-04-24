import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin


class AssignmentKind(str, enum.Enum):
    PROJECT_MEMBER = "project_member"
    TASK_ASSIGNEE = "task_assignee"


class Assignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "assignments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    kind: Mapped[AssignmentKind] = mapped_column(Enum(AssignmentKind), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")

    project = relationship("Project", back_populates="assignments")
    task = relationship("Task", back_populates="assignments")
    user = relationship("User", back_populates="assignments")
