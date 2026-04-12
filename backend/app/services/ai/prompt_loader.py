"""Load system prompts: custom from DB if set, otherwise defaults from prompts.py."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability_profile import AIConfig
from app.services.ai import prompts as defaults

FIELD_MAP = {
    "task_assign": ("prompt_task_assign", defaults.TASK_ASSIGNMENT_SYSTEM),
    "capability": ("prompt_capability", defaults.CAPABILITY_ANALYSIS_SYSTEM),
    "risk": ("prompt_risk", defaults.RISK_ANALYSIS_SYSTEM),
    "estimate": ("prompt_estimate", defaults.TASK_ESTIMATE_SYSTEM),
    "decompose": ("prompt_decompose", defaults.TASK_DECOMPOSE_SYSTEM),
}


async def get_system_prompt(db: AsyncSession, prompt_key: str) -> str:
    """Get system prompt by key. Returns custom if set, else default."""
    field_name, default_value = FIELD_MAP.get(prompt_key, (None, ""))
    if not field_name:
        return default_value

    result = await db.execute(select(getattr(AIConfig, field_name)).where(AIConfig.id == 1))
    custom = result.scalar_one_or_none()
    return custom or default_value
