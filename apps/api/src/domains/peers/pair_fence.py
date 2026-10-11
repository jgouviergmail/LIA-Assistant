"""Canonical account locks serialize creation even while no pair row exists."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User


async def lock_peer_pair(db: AsyncSession, first: UUID, second: UUID) -> None:
    """Lock the canonical parent order, without holding locks over external work."""
    await db.execute(
        select(User.id).where(User.id.in_({first, second})).order_by(User.id).with_for_update()
    )
