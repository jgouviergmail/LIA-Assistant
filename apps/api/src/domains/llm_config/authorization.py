"""Current administrative authority held through a configuration's final write."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_inactive
from src.core.security.authorization import require_superuser
from src.domains.users.repository import UserRepository


async def lock_current_admin(
    db: AsyncSession, admin_id: UUID, *, action: str = "update LLM configuration"
) -> None:
    """Recheck a fresh row after any catalogue wait, before committing an effect."""
    admin = await UserRepository(db).get_by_id_for_preference_update(admin_id)
    if admin is None:
        raise_user_inactive(admin_id)
    require_superuser(admin, action)
