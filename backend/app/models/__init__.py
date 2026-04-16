import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )


from app.models.user import User  # noqa: E402, F401
from app.models.project import Project, ProjectMember  # noqa: E402, F401
from app.models.task import Task, TaskAssignee, TaskRequiredSkill  # noqa: E402, F401
from app.models.skill import Skill, UserSkill  # noqa: E402, F401
from app.models.task_progress import TaskProgress  # noqa: E402, F401
from app.models.capability_profile import CapabilityProfile, AIConfig  # noqa: E402, F401
from app.models.permission import RolePermission  # noqa: E402, F401
