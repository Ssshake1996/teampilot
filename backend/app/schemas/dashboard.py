import uuid
from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_tasks: int
    in_progress_tasks: int
    overdue_tasks: int
    completion_rate: float  # 0-100


class ProjectProgress(BaseModel):
    project_id: uuid.UUID
    project_name: str
    total_tasks: int
    completed_tasks: int
    progress_pct: float


class TeamWorkload(BaseModel):
    user_id: uuid.UUID
    full_name: str
    avatar_url: str | None = None
    workload_hours: float
    assigned_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    overdue_tasks: int
    fallback_task_count: int = 0
    fallback_hours: float = 0.0


class RecentActivity(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    project_id: uuid.UUID
    user_name: str
    task_title: str
    project_name: str
    progress_pct: int
    note: str | None = None
    created_at: datetime
