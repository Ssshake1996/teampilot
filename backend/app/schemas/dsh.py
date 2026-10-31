import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.models.task import TaskPriority


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PlannedTask(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    goal: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=8000)
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    estimated_hours: float | None = Field(default=None, ge=0, le=100000)
    start_date: datetime | None = None
    deadline: datetime | None = None
    children: list["PlannedTask"] = Field(default_factory=list, max_length=100)


class ProjectPlan(StrictModel):
    kind: Literal["project_plan"]
    name: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=8000)
    start_date: date | None = None
    end_date: date | None = None
    tasks: list[PlannedTask] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded_tree(self):
        count = 0
        stack = [(task, 1) for task in self.tasks]
        while stack:
            task, depth = stack.pop()
            count += 1
            if count > 200 or depth > 8:
                raise ValueError("Plan exceeds 200 tasks or 8 levels")
            stack.extend((child, depth + 1) for child in task.children)
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Project end precedes start")
        return self


class ProgressEntry(StrictModel):
    task_id: uuid.UUID
    progress_pct: Annotated[StrictInt, Field(ge=0, le=100)]
    note: str | None = Field(default=None, max_length=8000)
    hours_spent: float | None = Field(default=None, ge=0, le=100000)


class ProgressDraft(StrictModel):
    kind: Literal["progress"]
    project_id: uuid.UUID
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    updates: list[ProgressEntry] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_tasks(self):
        if len({item.task_id for item in self.updates}) != len(self.updates):
            raise ValueError("Duplicate task updates")
        return self


class TaskPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    goal: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=8000)
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    estimated_hours: float | None = Field(default=None, ge=0, le=100000)
    start_date: datetime | None = None
    deadline: datetime | None = None
    weight: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one changed field is required")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Title cannot be null")
        return self


class TaskUpdateDraft(StrictModel):
    kind: Literal["task_update"]
    project_id: uuid.UUID
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    task_id: uuid.UUID
    patch: TaskPatch


class TaskCreateDraft(StrictModel):
    kind: Literal["task_create"]
    project_id: uuid.UUID
    revision: str = Field(pattern="^[a-f0-9]{64}$")
    parent_task_id: uuid.UUID | None = None
    tasks: list[PlannedTask] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded_tree(self):
        ProjectPlan(kind="project_plan", name="validation", tasks=self.tasks)
        return self


DraftPayload = Annotated[ProjectPlan | ProgressDraft | TaskUpdateDraft | TaskCreateDraft, Field(discriminator="kind")]


class DraftCreate(StrictModel):
    payload: DraftPayload


class DraftApprove(StrictModel):
    payload_hash: str = Field(pattern="^[a-f0-9]{64}$")


class DraftCommit(StrictModel):
    confirmation_token: str = Field(min_length=64, max_length=64)
