import uuid
from datetime import datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    role: str
    department: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    department: str | None = None
    bio: str | None = None


class UserWorkload(BaseModel):
    user_id: uuid.UUID
    full_name: str
    total_tasks: int
    in_progress_tasks: int
    overdue_tasks: int
    estimated_hours: float
    actual_hours: float
