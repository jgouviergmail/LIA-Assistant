"""Persistence of habit proposals (ADR-375).

Every transition is ONE conditional statement on the row's current status, so
two actors never overwrite each other: the nightly sync only refreshes or
removes an OPEN row, only reopens a dismissed or accepted one whose date has
passed, and a decision only lands on an OPEN row of its owner (the click that
loses a race reads None, never a second decision). A refusal is never touched
again but by « forget everything » (``forgetting.forget_habit_data``).

The chat's showing is claimed under the same owner lock, taken WITHOUT waiting:
an answer never waits for a card (``claim_chat_showing``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.habits.models import HabitProposal, ProposalStatus
from src.domains.users.models import User

#: Statuses a nightly sync may reopen once their date has passed.
_REOPENABLE = (ProposalStatus.DISMISSED.value, ProposalStatus.ACCEPTED.value)


class HabitProposalRepository(BaseRepository[HabitProposal]):
    """Reads and conditional transitions of ``habit_proposals``."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to the caller's session (the caller commits).

        Args:
            db: The session.
        """
        super().__init__(db, HabitProposal)

    async def list_for_user(self, user_id: UUID) -> list[HabitProposal]:
        """Every proposal of a person, whatever its status, oldest first.

        Args:
            user_id: Owner.

        Returns:
            The rows.
        """
        result = await self.db.execute(
            select(HabitProposal)
            .where(HabitProposal.user_id == user_id)
            .order_by(HabitProposal.created_at, HabitProposal.id)
        )
        return list(result.scalars().all())

    async def lock_owner(self, user_id: UUID) -> None:
        """Take the person's row before any proposal of theirs is decided.

        The order every decision follows — the owner, then the proposal — is
        the order the acts it carries out take too (a routine created, the
        notification preferences changed): one order, no deadlock between two
        clicks or between a click and the nightly sync.

        Args:
            user_id: Owner.
        """
        await self.db.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def try_lock_owner(self, user_id: UUID) -> bool:
        """Take the person's row only if nobody holds it — never wait for it.

        The same lock as :meth:`lock_owner`, so a showing and a decision are
        serialised; but where a click may wait its turn, an answer may not.
        Anything holding the person's row makes this return False: a decision
        in flight, another turn of the same person, the nightly recompute
        (which fences the owner first), a write that references the person.

        Args:
            user_id: Owner.

        Returns:
            True when the lock is now held by this transaction.
        """
        locked = await self.db.scalar(
            select(User.id).where(User.id == user_id).with_for_update(skip_locked=True)
        )
        return locked is not None

    async def claim_chat_showing(
        self,
        user_id: UUID,
        *,
        preferred: Sequence[tuple[str, str]],
        now: datetime,
        gap: timedelta,
        repeat: timedelta,
    ) -> HabitProposal | None:
        """Choose the one proposal a chat answer shows, and stamp it as shown.

        At most one per ``gap``, whatever became of it since; the first open
        one among ``preferred`` (the turn's own domain) not shown within
        ``repeat``, else the oldest open one the chat never showed. Everything
        happens under the owner's lock taken without waiting: when the person
        is busy, nothing is shown this turn.

        Args:
            user_id: Owner.
            preferred: ``(kind, key)`` identities matching the turn, if any.
            now: The showing instant (UTC).
            gap: Least time between two showings.
            repeat: Least time before one proposal is shown again.

        Returns:
            The stamped row, or None when nothing is shown.
        """
        if not await self.try_lock_owner(user_id):
            return None
        recent = await self.db.scalar(
            select(HabitProposal.id)
            .where(HabitProposal.user_id == user_id, HabitProposal.chat_shown_at > now - gap)
            .limit(1)
        )
        if recent is not None:
            return None
        chosen = await self._showable(user_id, preferred, shown_before=now - repeat)
        if chosen is None:
            return None
        result = await self.db.execute(
            update(HabitProposal)
            .where(
                HabitProposal.id == chosen,
                HabitProposal.status == ProposalStatus.OPEN.value,
            )
            .values(chat_shown_at=now)
            .returning(HabitProposal)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def _showable(
        self, user_id: UUID, preferred: Sequence[tuple[str, str]], *, shown_before: datetime
    ) -> UUID | None:
        """The open proposal a showing would take: the turn's own first, else a new one."""
        owned_open = (
            HabitProposal.user_id == user_id,
            HabitProposal.status == ProposalStatus.OPEN.value,
        )
        oldest_first = (HabitProposal.created_at, HabitProposal.id)
        if preferred:
            matching: UUID | None = await self.db.scalar(
                select(HabitProposal.id)
                .where(
                    *owned_open,
                    tuple_(HabitProposal.kind, HabitProposal.key).in_(list(preferred)),
                    (HabitProposal.chat_shown_at.is_(None))
                    | (HabitProposal.chat_shown_at <= shown_before),
                )
                .order_by(*oldest_first)
                .limit(1)
            )
            if matching is not None:
                return matching
        never_shown: UUID | None = await self.db.scalar(
            select(HabitProposal.id)
            .where(*owned_open, HabitProposal.chat_shown_at.is_(None))
            .order_by(*oldest_first)
            .limit(1)
        )
        return never_shown

    async def get_owned(self, proposal_id: UUID, user_id: UUID) -> HabitProposal | None:
        """One proposal, scoped to its owner at the query (a stranger's reads as absent).

        Args:
            proposal_id: The row.
            user_id: The person asking.

        Returns:
            The fresh row, or None.
        """
        result = await self.db.execute(
            select(HabitProposal)
            .where(HabitProposal.id == proposal_id, HabitProposal.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def open(self, user_id: UUID, kind: str, key: str, payload: dict[str, Any]) -> bool:
        """Open a proposal, unless the person already has one with this identity.

        Args:
            user_id: Owner.
            kind: ``ProposalKind`` value.
            key: Identity within the kind.
            payload: The facts.

        Returns:
            True when a row was created.
        """
        statement = (
            pg_insert(HabitProposal)
            .values(
                user_id=user_id,
                kind=kind,
                key=key,
                payload=payload,
                status=ProposalStatus.OPEN.value,
            )
            .on_conflict_do_nothing(constraint="uq_habit_proposals_user_kind_key")
            .returning(HabitProposal.id)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def refresh_open(self, proposal_id: UUID, payload: dict[str, Any]) -> bool:
        """Replace an OPEN proposal's facts.

        Args:
            proposal_id: The row.
            payload: The new facts (a NEW dict, never the row's mutated in place).

        Returns:
            True when the row was still open.
        """
        result = await self.db.execute(
            update(HabitProposal)
            .where(
                HabitProposal.id == proposal_id,
                HabitProposal.status == ProposalStatus.OPEN.value,
            )
            .values(payload=payload)
            .returning(HabitProposal.id)
        )
        return result.scalar_one_or_none() is not None

    async def reopen(self, proposal_id: UUID, payload: dict[str, Any], *, now: datetime) -> bool:
        """Reopen a dismissed or accepted proposal whose date has passed.

        Args:
            proposal_id: The row.
            payload: The facts it reopens with.
            now: The instant compared with ``resurface_after``.

        Returns:
            True when the row reopened.
        """
        result = await self.db.execute(
            update(HabitProposal)
            .where(
                HabitProposal.id == proposal_id,
                HabitProposal.status.in_(_REOPENABLE),
                HabitProposal.resurface_after.is_not(None),
                HabitProposal.resurface_after <= now,
            )
            .values(
                status=ProposalStatus.OPEN.value,
                payload=payload,
                resurface_after=None,
                decided_at=None,
                chat_shown_at=None,
            )
            .returning(HabitProposal.id)
        )
        return result.scalar_one_or_none() is not None

    async def withdraw_open(self, proposal_id: UUID) -> bool:
        """Remove an OPEN proposal that stopped being true.

        Args:
            proposal_id: The row.

        Returns:
            True when an open row was removed.
        """
        result = await self.db.execute(
            delete(HabitProposal)
            .where(
                HabitProposal.id == proposal_id,
                HabitProposal.status == ProposalStatus.OPEN.value,
            )
            .returning(HabitProposal.id)
        )
        return result.scalar_one_or_none() is not None

    async def decide(
        self,
        proposal_id: UUID,
        user_id: UUID,
        status: ProposalStatus,
        resurface_after: datetime | None,
        *,
        now: datetime,
    ) -> HabitProposal | None:
        """Record the person's decision — only on an OPEN proposal of theirs.

        Args:
            proposal_id: The row.
            user_id: The person deciding (a stranger's id matches nothing).
            status: ``accepted``, ``dismissed`` or ``refused``.
            resurface_after: When it may reopen; None for a refusal.
            now: The decision instant.

        Returns:
            The decided row, or None when it was not open (already decided,
            withdrawn, or not theirs).
        """
        result = await self.db.execute(
            update(HabitProposal)
            .where(
                HabitProposal.id == proposal_id,
                HabitProposal.user_id == user_id,
                HabitProposal.status == ProposalStatus.OPEN.value,
            )
            .values(status=status.value, resurface_after=resurface_after, decided_at=now)
            .returning(HabitProposal)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def page_open(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[HabitProposal], int]:
        """One page of OPEN proposals and their exact total, from ONE statement.

        Args:
            user_id: Owner.
            limit: Page size.
            offset: Rows skipped.

        Returns:
            ``(rows, total)`` — newest first, the total stated even past the end.
        """
        owned_open = (
            HabitProposal.user_id == user_id,
            HabitProposal.status == ProposalStatus.OPEN.value,
        )
        total = (
            select(func.count())
            .select_from(HabitProposal)
            .where(*owned_open)
            .scalar_subquery()
            .label("total")
        )
        rows = (
            await self.db.execute(
                select(HabitProposal, total)
                .where(*owned_open)
                .order_by(HabitProposal.created_at.desc(), HabitProposal.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        if rows:
            return [row[0] for row in rows], int(rows[0][1])
        return [], await self.count_open(user_id)

    async def count_open(self, user_id: UUID) -> int:
        """How many proposals wait for the person's decision.

        Args:
            user_id: Owner.

        Returns:
            The exact count.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(HabitProposal)
            .where(
                HabitProposal.user_id == user_id,
                HabitProposal.status == ProposalStatus.OPEN.value,
            )
        )
        return int(result.scalar_one())

    async def refusal_counts(self, user_id: UUID) -> dict[str, int]:
        """Refused proposals by kind — the learning from decisions.

        Args:
            user_id: Owner.

        Returns:
            ``{kind: count}`` for kinds refused at least once.
        """
        result = await self.db.execute(
            select(HabitProposal.kind, func.count())
            .where(
                HabitProposal.user_id == user_id,
                HabitProposal.status == ProposalStatus.REFUSED.value,
            )
            .group_by(HabitProposal.kind)
        )
        return {kind: int(count) for kind, count in result.all()}
