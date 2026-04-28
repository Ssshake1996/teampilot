import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.project import ProjectStatus, ProjectRole


class ProjectCreate(BaseModel):
    name: str
    goal: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    goal: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    goal: str | None = None
    description: str | None = None
    status: ProjectStatus
    owner_id: uuid.UUID
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime
    task_count: int = 0
    completed_count: int = 0
    member_count: int = 0

    model_config = {"from_attributes": True}


class ProjectMemberAdd(BaseModel):
    user_id: uuid.UUID
    role_in_project: ProjectRole = ProjectRole.MEMBER


class ProjectMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    role_in_project: ProjectRole

    model_config = {"from_attributes": True}
