import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin


class ConnectorAuthType(str, enum.Enum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    BASIC = "basic"
    DYNAMIC_TOKEN = "dynamic_token"


class TaskDataSkillStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class SkillRunStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


class DataConnector(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "data_connectors"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_type: Mapped[ConnectorAuthType] = mapped_column(
        Enum(ConnectorAuthType), default=ConnectorAuthType.NONE, nullable=False
    )
    auth_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    task_data_skills = relationship("TaskDataSkill", back_populates="connector")


class TaskDataSkill(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_data_skills"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=False, index=True
    )
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_connectors.id"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    natural_language: Mapped[str] = mapped_column(Text, nullable=False)
    skill_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[TaskDataSkillStatus] = mapped_column(
        Enum(TaskDataSkillStatus), default=TaskDataSkillStatus.DRAFT, nullable=False, index=True
    )

    task = relationship("Task", back_populates="data_skills")
    connector = relationship("DataConnector", back_populates="task_data_skills")
    created_by = relationship("User", foreign_keys=[created_by_id])
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])
    runs = relationship("SkillRun", back_populates="task_data_skill", cascade="all, delete-orphan")


class SkillRun(Base, UUIDMixin):
    __tablename__ = "skill_runs"

    task_data_skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("task_data_skills.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[SkillRunStatus] = mapped_column(
        Enum(SkillRunStatus), nullable=False, index=True
    )
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ai_analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    suggested_progress_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    task_data_skill = relationship("TaskDataSkill", back_populates="runs")
    task = relationship("Task", back_populates="skill_runs")
    actor = relationship("User")
