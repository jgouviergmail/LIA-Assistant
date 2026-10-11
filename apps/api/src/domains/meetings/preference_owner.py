"""Serialize preference saves and deletion of their referenced user templates."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_not_found
from src.domains.users.repository import UserRepository


async def lock_meeting_preference_owner(db: AsyncSession, user_id: UUID) -> None:
    if await UserRepository(db).get_by_id_for_preference_update(user_id) is None:
        raise_user_not_found(user_id)
