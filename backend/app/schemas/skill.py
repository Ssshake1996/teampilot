import uuid

from pydantic import BaseModel


class SkillCreate(BaseModel):
    name: str
    category: str | None = None
    description: str | None = None


class SkillOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None = None
    description: str | None = None

    model_config = {"from_attributes": True}


class UserSkillUpdate(BaseModel):
    skill_id: uuid.UUID
    proficiency: int  # 1-5


class UserSkillOut(BaseModel):
    skill_id: uuid.UUID
    skill_name: str
    category: str | None = None
    proficiency: int

    model_config = {"from_attributes": True}
