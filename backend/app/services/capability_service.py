import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability_profile import CapabilityProfile


async def get_capability_profile(db: AsyncSession, user_id: uuid.UUID) -> CapabilityProfile | None:
    result = await db.execute(
        select(CapabilityProfile).where(CapabilityProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()
