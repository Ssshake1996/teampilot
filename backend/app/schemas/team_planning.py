import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanningInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class WeekFields(PlanningInput):
    week_start: date

    @field_validator("week_start")
    @classmethod
    def monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        return value


class CapacityInput(PlanningInput):
    user_id: uuid.UUID
    available_hours: float = Field(ge=0, le=168, multiple_of=0.1)
    note: str = Field(default="", max_length=2000)


class AllocationInput(WeekFields):
    task_id: uuid.UUID
    user_id: uuid.UUID
    hours: float = Field(gt=0, le=168, multiple_of=0.1)


class MilestoneInput(PlanningInput):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    owner_id: uuid.UUID
    due_date: date
    task_ids: list[uuid.UUID] = Field(default_factory=list)


class MilestoneUpdate(PlanningInput):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    task_ids: list[uuid.UUID] | None = None


class DependencyInput(PlanningInput):
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID


class BaselineInput(PlanningInput):
    label: str = Field(min_length=1, max_length=200)


class CommitmentInput(WeekFields):
    task_id: uuid.UUID
    owner_id: uuid.UUID
    expected_outcome: str = Field(min_length=1, max_length=4000)


class CommitmentUpdate(PlanningInput):
    expected_outcome: str | None = Field(default=None, min_length=1, max_length=4000)
    outcome_note: str | None = Field(default=None, max_length=4000)


class RetroAction(PlanningInput):
    title: str = Field(min_length=1, max_length=300)
    owner_id: uuid.UUID
    deadline: datetime
    acceptance_criteria: str = Field(default="", max_length=8000)


class RetrospectiveInput(WeekFields):
    project_id: uuid.UUID
    summary: str = Field(min_length=1, max_length=8000)
    decisions: str = Field(default="", max_length=8000)
    actions: list[RetroAction] = Field(default_factory=list, max_length=30)
