import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.data_skill import ConnectorAuthType, SkillRunStatus, TaskDataSkillStatus


class DataConnectorBase(BaseModel):
    name: str
    key: str
    description: str | None = None
    base_url: str
    auth_type: ConnectorAuthType = ConnectorAuthType.NONE
    auth_config_json: dict = Field(default_factory=dict)
    headers_json: dict = Field(default_factory=dict)
    timeout_seconds: int = 30
    verify_tls: bool = False
    is_enabled: bool = True


class DataConnectorCreate(DataConnectorBase):
    pass


class DataConnectorUpdate(BaseModel):
    name: str | None = None
    key: str | None = None
    description: str | None = None
    base_url: str | None = None
    auth_type: ConnectorAuthType | None = None
    auth_config_json: dict | None = None
    headers_json: dict | None = None
    timeout_seconds: int | None = None
    verify_tls: bool | None = None
    is_enabled: bool | None = None


class DataConnectorOut(DataConnectorBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskDataSkillGenerateRequest(BaseModel):
    natural_language: str
    connector_id: uuid.UUID | None = None


class TaskDataSkillUpdate(BaseModel):
    natural_language: str | None = None
    connector_id: uuid.UUID | None = None
    skill_json: dict | None = None


class TaskDataSkillOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    connector_id: uuid.UUID | None = None
    connector_name: str | None = None
    created_by_id: uuid.UUID
    confirmed_by_id: uuid.UUID | None = None
    confirmed_at: datetime | None = None
    natural_language: str
    skill_json: dict
    status: TaskDataSkillStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillRunRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    use_ai: bool = True


class SkillRunOut(BaseModel):
    id: uuid.UUID
    task_data_skill_id: uuid.UUID
    task_id: uuid.UUID
    actor_id: uuid.UUID
    status: SkillRunStatus
    request_json: dict
    response_json: dict
    metrics_json: dict
    ai_analysis_json: dict
    suggested_progress_pct: int | None = None
    suggested_note: str | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SkillRunAdoptRequest(BaseModel):
    progress_pct: int | None = None
    note: str | None = None
    hours_spent: float | None = None
