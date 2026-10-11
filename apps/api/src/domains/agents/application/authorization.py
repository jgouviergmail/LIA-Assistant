"""Current account authority, shared by preparation, reads and execution."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.models import User


def authorize_actor(
    actor: User | None, *, administrative: bool = False, owner_id: UUID | None = None
) -> User:
    """Validate freshly loaded facts; model-supplied identity is never accepted."""
    if actor is None or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    if administrative and not actor.is_superuser:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    if owner_id is not None and actor.id != owner_id:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    return actor


async def load_actor(db: AsyncSession, user_id: UUID, *, administrative: bool = False) -> User:
    """Refresh the identity map as well as the query; old role snapshots are unsafe."""
    actor: User | None = await db.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    return authorize_actor(actor, administrative=administrative)
