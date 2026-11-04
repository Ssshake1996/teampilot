import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class ResponsibilityUpdate(BaseModel):
    owner_id: uuid.UUID
    collaborator_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    reviewer_id: uuid.UUID
    acceptance_criteria: str = Field(min_length=1, max_length=10000)
    change_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("acceptance_criteria", "change_reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("内容不能为空")
        return value.strip()


class HandoverAccept(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class DeliveryUpdate(BaseModel):
    deliverable_url: str | None = Field(default=None, max_length=2048)
    deliverable_note: str | None = Field(default=None, max_length=10000)

    @field_validator("deliverable_url")
    @classmethod
    def evidence_url(cls, value):
        if not value or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("成果链接须为不含账号密码的 HTTP/HTTPS 地址")
        return value.strip()


class ReviewRequest(BaseModel):
    decision: Literal["accept", "return"]
    note: str = Field(default="", max_length=10000)


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=10000)
    owner_id: uuid.UUID
    next_action: str = Field(min_length=1, max_length=10000)
    due_at: datetime

    @field_validator("title", "reason", "next_action")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("内容不能为空")
        return value.strip()


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=10000)
    owner_id: uuid.UUID | None = None
    next_action: str | None = Field(default=None, min_length=1, max_length=10000)
    due_at: datetime | None = None
    state: Literal["open", "resolved"] | None = None
    resolution: str | None = Field(default=None, max_length=10000)

    @field_validator("title", "reason", "next_action")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("内容不能为空")
        return value.strip() if value else value
