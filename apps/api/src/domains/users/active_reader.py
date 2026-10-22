"""A short owner fence for bounded native readers, without loading a profile."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.models import User


async def require_active_owner_read(db: AsyncSession, owner: UUID) -> None:
    """Hold a share lock on an active account for the read, or refuse it.

    Args:
        db: The session to read with.
        owner: The account.

    Raises:
        AuthorizationError: The account is inactive or deleted (``FORBIDDEN``).
    """
    actor = await db.scalar(
        select(User.id)
        .where(
            User.id == owner,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .with_for_update(read=True)
    )
    if actor is None:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
