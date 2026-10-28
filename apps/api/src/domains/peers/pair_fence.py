"""Canonical account locks serialize creation even while no pair row exists."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User


async def lock_peer_pair(db: AsyncSession, first: UUID, second: UUID) -> None:
    """Lock the canonical parent order, without holding locks over external work.

    The fence is ``FOR NO KEY UPDATE``: it orders every fence taker (block,
    unblock, requests, the World game policy) and every UPDATE/DELETE of the two
    accounts, never a row merely REFERENCING them. A foreign-key check takes
    ``FOR KEY SHARE``, which a ``FOR UPDATE`` fence refuses: a share writer that
    already held the pair row then waited for the fence while the fence holder
    waited for that pair row — PostgreSQL aborted one of them (40P01).

    Args:
        db: The caller's session; the fence lasts until its transaction ends.
        first: One account of the pair.
        second: The other account.
    """
    await db.execute(
        select(User.id)
        .where(User.id.in_({first, second}))
        .order_by(User.id)
        .with_for_update(key_share=True)
    )
