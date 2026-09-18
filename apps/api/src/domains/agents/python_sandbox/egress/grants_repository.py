"""Reads and writes of the egress grants (ADR-298).

A page and its exact total come from ONE ``WHERE`` (ADR-185); the cap is an
aggregate over the whole set, never a page's length; and answering the card
twice for one host UPDATES the scope — the unique constraint is the identity,
and an upsert is how it is honoured without a race between a read and an
insert.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.agents.python_sandbox.egress.models import SandboxEgressGrant


class EgressGrantRepository(BaseRepository[SandboxEgressGrant]):
    """The grants of one account."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, SandboxEgressGrant)

    async def upsert(
        self, user_id: UUID, host: str, *, share_turn_data: bool
    ) -> SandboxEgressGrant:
        """Record the person's decision for a host, replacing an older one.

        Args:
            user_id: The account.
            host: The exact hostname.
            share_turn_data: The scope chosen on the card.

        Returns:
            The row, created or updated.
        """
        now = datetime.now(UTC)
        statement = (
            pg_insert(SandboxEgressGrant)
            .values(user_id=user_id, host=host, share_turn_data=share_turn_data)
            .on_conflict_do_update(
                constraint="uq_sandbox_egress_grants_user_host",
                set_={"share_turn_data": share_turn_data, "updated_at": now},
            )
            .returning(SandboxEgressGrant)
        )
        # `populate_existing`: the identity map may already hold this row from
        # an earlier read in the same session, and RETURNING would otherwise
        # hand that instance back with its STALE scope (measured on real
        # PostgreSQL 2026-09-18: the second upsert reported the first answer).
        row = (
            await self.db.execute(statement, execution_options={"populate_existing": True})
        ).scalar_one()
        await self.db.flush()
        return row

    async def scopes_for_user(self, user_id: UUID) -> dict[str, bool]:
        """``{host: share_turn_data}`` — what the classification reads."""
        statement = select(SandboxEgressGrant.host, SandboxEgressGrant.share_turn_data).where(
            SandboxEgressGrant.user_id == user_id
        )
        return {host: bool(share) for host, share in (await self.db.execute(statement)).all()}

    async def count_for_user(self, user_id: UUID) -> int:
        """How many grants the account keeps — the figure the cap reads."""
        statement = select(func.count()).where(SandboxEgressGrant.user_id == user_id)
        return int((await self.db.execute(statement)).scalar_one())

    async def list_page(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[SandboxEgressGrant], int]:
        """One page, newest first, and the EXACT total behind it (ADR-185)."""
        where = SandboxEgressGrant.user_id == user_id
        rows = (
            (
                await self.db.execute(
                    select(SandboxEgressGrant)
                    .where(where)
                    .order_by(SandboxEgressGrant.created_at.desc(), SandboxEgressGrant.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        total = int((await self.db.execute(select(func.count()).where(where))).scalar_one())
        return rows, total

    async def get_for_user(self, user_id: UUID, grant_id: UUID) -> SandboxEgressGrant | None:
        """One grant, only if it is this account's."""
        statement = select(SandboxEgressGrant).where(
            SandboxEgressGrant.id == grant_id, SandboxEgressGrant.user_id == user_id
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def set_scope(
        self, user_id: UUID, grant_id: UUID, *, share_turn_data: bool
    ) -> SandboxEgressGrant | None:
        """Change a grant's scope from the settings page."""
        statement = (
            update(SandboxEgressGrant)
            .where(SandboxEgressGrant.id == grant_id, SandboxEgressGrant.user_id == user_id)
            .values(share_turn_data=share_turn_data, updated_at=datetime.now(UTC))
            .returning(SandboxEgressGrant)
        )
        row = (
            await self.db.execute(statement, execution_options={"populate_existing": True})
        ).scalar_one_or_none()
        await self.db.flush()
        return row

    async def touch(self, user_id: UUID, hosts: Iterable[str], *, when: datetime) -> None:
        """Stamp the last use of the grants a run relied on."""
        names = list(hosts)
        if not names:
            return
        await self.db.execute(
            update(SandboxEgressGrant)
            .where(SandboxEgressGrant.user_id == user_id, SandboxEgressGrant.host.in_(names))
            .values(last_used_at=when)
        )

    async def delete_for_user(self, user_id: UUID, grant_id: UUID) -> bool:
        """Revoke a grant; False when it is not this account's (or already gone)."""
        result = await self.db.execute(
            delete(SandboxEgressGrant).where(
                SandboxEgressGrant.id == grant_id, SandboxEgressGrant.user_id == user_id
            )
        )
        await self.db.flush()
        # The bookmarks repository's reading: a DELETE returns a CursorResult
        # whose rowcount the generic Result type does not declare.
        return bool(getattr(result, "rowcount", 0))


__all__ = ["EgressGrantRepository"]
