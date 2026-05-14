import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.task import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    title: str
    goal: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    parent_task_id: uuid.UUID | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    estimated_hours: float | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    goal: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_ids: list[uuid.UUID] | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    estimated_hours: float | None = None
    actual_hours: float | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    goal: str | None = None
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    assignee_name: str | None = None
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    assignee_names: list[str] = Field(default_factory=list)
    creator_id: uuid.UUID
    parent_task_id: uuid.UUID | None = None
    weight: float = 1.0
    estimated_hours: float | None = None
    actual_hours: float | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    completed_at: datetime | None = None
    signed_off_by_id: uuid.UUID | None = None
    signed_off_by_name: str | None = None
    signed_off_at: datetime | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    progress_pct: int = 0
    is_deleted: bool = False
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskAssign(BaseModel):
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)


class TaskReorder(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus | None = None
    sort_order: int


class TaskProgressCreate(BaseModel):
    progress_pct: int
    note: str | None = None
    hours_spent: float | None = None


class TaskProgressOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    progress_pct: int
    note: str | None = None
    hours_spent: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
