import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class ProjectAccessPolicy(Base, TimestampMixin):
    __tablename__ = "project_access_policies"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), primary_key=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="company")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
