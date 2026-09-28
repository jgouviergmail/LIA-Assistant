"""Serialise one account's transactions in one scope (ADR-316, ADR-319).

Two writers must count and write under the same lock or a race slips past a
ceiling: the image shares of one sender (two daily caps, ADR-316) and the files
one account keeps (two keeping ceilings, ADR-319). Both hold a PostgreSQL
advisory lock for the length of their transaction, keyed by a scope and the
account — one implementation, so the two cannot drift on the three choices
that make it correct:

- **Transaction-scoped** (``pg_advisory_xact_lock``), never session-scoped: the
  commit or the rollback releases it, including on a pooled connection that is
  reused afterwards (``setup_lock.py`` releases its session lock by hand for
  exactly that reason).
- **Hashed to 64 bits** (``hashtextextended``): the 32-bit ``hashtext`` makes a
  collision between two accounts likely at scale, and a collision serialises
  two strangers — harmless for correctness, a latency cost for nothing.
- **Named by a scope**: two features never contend with each other for one
  account.

This is not a cache key: its name never reaches Redis, a conversation reset
cannot touch it, and it disappears with the transaction that held it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def hold_owner_lock(db: AsyncSession, scope: str, owner_id: uuid.UUID) -> None:
    """Hold ``scope``'s lock for ``owner_id`` until the current transaction ends.

    A second transaction asking for the same scope and owner waits here until
    the first commits or rolls back; other owners and other scopes never wait.

    Args:
        db: Session whose CURRENT transaction holds the lock.
        scope: Stable name of what is serialised (``"peer_image_share"``).
        owner_id: The account the scope is serialised for.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{scope}:{owner_id}"},
    )
