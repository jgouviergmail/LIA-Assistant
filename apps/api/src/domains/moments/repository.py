"""Data access for anticipated moments — every transition in one statement.

A moment row is a durable claim on a future instant, so it obeys the rules every
durable claim in this repository obeys:

- **the identity is filed once.** The detector re-reads the same calendar window
  at every pass, so the insert conflicts on ``(user_id, kind, source_ref)`` and
  does nothing rather than filing the same meeting twenty times.
- **the claim is one statement.** ``FOR UPDATE SKIP LOCKED`` picks the row and a
  conditional ``UPDATE`` takes it, in the same transaction: a claim followed by
  work decided outside the claiming statement is the forbidden shape.
- **every settle quotes its owner.** A worker killed mid-flight comes back and
  writes; conditioned on ``claim_owner`` its write matches nothing instead of
  overwriting a state the sweep has since decided.
- **nothing is SELECT-then-mutate-in-Python.** Expiry and purge are bounded
  statements.
- **a claim that stops answering is given back.** A worker killed between the
  claim's commit and the settle's leaves a row no other statement can reach:
  ``expire_stale`` reads ``pending``, ``purge_settled`` reads settled states,
  and ``claim_due`` reads ``pending`` — so the row sat in ``claimed`` for ever
  (measured on a real server 2026-09-11: still there at +365 days). The end is
  read from the claim's AGE, never from the window, which is what lets the
  moment be tried again while it is still worth something; a row whose window
  has closed too is reclaimed and then expired in the same pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.moments.models import (
    MomentSkipReason,
    MomentState,
    ProactiveMoment,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: States a row can still leave: one statement of this module moves each of
#: them on, so neither accumulates.
LIVE_STATES: tuple[str, ...] = (
    MomentState.PENDING.value,
    MomentState.CLAIMED.value,
)

#: States a row can no longer leave — the purge's whole scope.
SETTLED_STATES: tuple[str, ...] = (
    MomentState.SERVED.value,
    MomentState.SKIPPED.value,
    MomentState.EXPIRED.value,
    MomentState.CANCELLED.value,
)


def assert_state_partition_complete() -> None:
    """Refuse to boot on a state that belongs to neither half (ADR-085).

    The two tuples must PARTITION ``MomentState``: every member in exactly one.
    A terminal state missing from ``SETTLED_STATES`` is invisible to the purge
    and accumulates for ever, which is the leak this module already paid for
    once — a claimed row nothing could reach. A live state missing from
    ``LIVE_STATES`` is the same defect wearing the other mask: nothing would
    move it on.

    Raises:
        RuntimeError: Naming what is unclassified or claimed twice.
    """
    live = set(LIVE_STATES)
    settled = set(SETTLED_STATES)
    known = {state.value for state in MomentState}

    unclassified = sorted(known - live - settled)
    both = sorted(live & settled)
    unknown = sorted((live | settled) - known)
    if unclassified or both or unknown:
        raise RuntimeError(
            "Moment state partition broken: "
            f"unclassified={unclassified}, in both halves={both}, "
            f"not a state={unknown}"
        )


# The boot carries this: every process that imports the repository checks it.
assert_state_partition_complete()


@dataclass(frozen=True, slots=True)
class MomentCandidate:
    """One moment a detector proposes.

    Frozen: a candidate describes what the detector saw at one instant. The
    insert may or may not file it — an identity already on file wins — so a
    mutable candidate would let a caller believe it changed a row it did not.

    Attributes:
        user_id: Whose moment.
        kind: A ``MomentKind`` value.
        source_ref: What it is about, in the source's own vocabulary.
        due_at: When there will be something to say (UTC, aware).
        not_after: When there no longer will be (UTC, aware).
        payload: Deduplication and scoring data — never the people involved.
    """

    user_id: UUID
    kind: str
    source_ref: str
    due_at: datetime
    not_after: datetime
    payload: dict[str, Any] = field(default_factory=dict)


class MomentRepository:
    """Every read and write of ``proactive_moments``."""

    def __init__(self, db: AsyncSession) -> None:
        """Args:
        db: Session of the caller's transaction. The caller commits.
        """
        self.db = db

    async def insert_candidates(self, candidates: list[MomentCandidate]) -> list[str]:
        """File what a detector proposed, skipping identities already on file.

        Returns the KINDS really filed rather than a count, because the caller
        counts a metric per kind: with a count it would have to guess which
        candidates won, and ``candidates[:n]`` is wrong the moment the conflict
        is anywhere but at the end of the list.

        Args:
            candidates: What the detectors produced this pass.

        Returns:
            One entry per row really created — never one per row proposed.
        """
        if not candidates:
            return []
        statement = (
            pg_insert(ProactiveMoment)
            .values(
                [
                    {
                        "user_id": candidate.user_id,
                        "kind": candidate.kind,
                        "source_ref": candidate.source_ref,
                        "due_at": candidate.due_at,
                        "not_after": candidate.not_after,
                        "payload": candidate.payload,
                        "state": MomentState.PENDING.value,
                    }
                    for candidate in candidates
                ]
            )
            .on_conflict_do_nothing(constraint="uq_proactive_moments_identity")
            .returning(ProactiveMoment.kind)
        )
        result = await self.db.execute(statement)
        return [str(kind) for kind in result.scalars().all()]

    async def claim_due(
        self,
        *,
        user_id: UUID,
        now: datetime,
        owner: str,
    ) -> ProactiveMoment | None:
        """Take the account's oldest due moment, or say there is none.

        The row is locked with ``SKIP LOCKED`` and taken by a conditional
        ``UPDATE`` in the same transaction, so two workers can never hold the
        same moment. The caller commits before doing any work with it: a run
        lasts minutes, and a database connection held that long is a connection
        nobody else can have.

        Args:
            user_id: Whose board of moments.
            now: The instant dueness is judged against.
            owner: The claim's owner token; every later settle quotes it.

        Returns:
            The claimed row, or None when nothing is due.
        """
        locked = (
            select(ProactiveMoment)
            .where(
                ProactiveMoment.user_id == user_id,
                ProactiveMoment.state == MomentState.PENDING.value,
                ProactiveMoment.due_at <= now,
                ProactiveMoment.not_after > now,
            )
            .order_by(ProactiveMoment.due_at.asc(), ProactiveMoment.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        candidate = (await self.db.execute(locked)).scalars().first()
        if candidate is None:
            return None

        taken = (
            update(ProactiveMoment)
            .where(
                ProactiveMoment.id == candidate.id,
                # Re-checked inside the UPDATE: between the scan and the write
                # another worker may have taken the row.
                ProactiveMoment.state == MomentState.PENDING.value,
            )
            .values(
                state=MomentState.CLAIMED.value,
                claim_owner=owner,
                claimed_at=now,
            )
            .returning(ProactiveMoment.id)
        )
        if (await self.db.execute(taken)).scalar_one_or_none() is None:
            return None
        await self.db.refresh(candidate)
        return candidate

    async def settle(
        self,
        moment_id: UUID,
        *,
        owner: str,
        state: MomentState,
        now: datetime,
        skip_reason: MomentSkipReason | None = None,
    ) -> bool:
        """Close a claimed moment, and only if this owner still holds it.

        Args:
            moment_id: The row to close.
            owner: The token this worker claimed it with.
            state: The settled state to write.
            now: When it settled.
            skip_reason: Required vocabulary when ``state`` is ``skipped``.

        Returns:
            True when the row was really closed; False when the claim had
            already moved on — a zombie's write must land on nothing.
        """
        statement = (
            update(ProactiveMoment)
            .where(
                ProactiveMoment.id == moment_id,
                ProactiveMoment.claim_owner == owner,
                ProactiveMoment.state == MomentState.CLAIMED.value,
            )
            .values(
                state=state.value,
                settled_at=now,
                skip_reason=None if skip_reason is None else skip_reason.value,
            )
            .returning(ProactiveMoment.id)
        )
        settled = (await self.db.execute(statement)).scalar_one_or_none() is not None
        if not settled:
            logger.info(
                "moment_settle_ignored",
                moment_id=str(moment_id),
                reason="the claim had already moved on",
            )
        return settled

    async def reclaim_stale(self, *, now: datetime, older_than: timedelta) -> int:
        """Give back the claims whose holder stopped answering.

        A moment is claimed, then served, then settled. Between the claim's
        commit and the settle's the worker can simply stop existing — killed
        mid-deploy, refused a connection, or raising something the sweep's
        per-account handler swallows. Nothing else in this module can reach the
        row afterwards, so without this it is lost for good.

        Back to ``pending`` rather than straight to a settled state, so a moment
        still inside its window is TRIED AGAIN rather than silently dropped; one
        whose window has closed is expired by :meth:`expire_stale` in the same
        pass, which is why housekeeping runs this first.

        The owner token is cleared with the claim: the dead worker's late write
        is conditioned on it and must match nothing, even after another worker
        has taken the row.

        Args:
            now: The instant the claim's age is judged against.
            older_than: How long a claim may legitimately take. Comfortably
                longer than a real serve — too short a lease hands the same
                moment to a second worker while the first is still speaking,
                which is the one failure worse than losing the row.

        Returns:
            How many claims were given back.
        """
        statement = (
            update(ProactiveMoment)
            .where(
                ProactiveMoment.state == MomentState.CLAIMED.value,
                ProactiveMoment.claimed_at.is_not(None),
                ProactiveMoment.claimed_at <= now - older_than,
            )
            .values(
                state=MomentState.PENDING.value,
                claim_owner=None,
                claimed_at=None,
            )
        )
        # ``rowcount``, not a RETURNING the caller would only count: this runs
        # every sweep for ever, and the ids it would allocate are read by
        # nobody. The ignore is the repository-wide shape for DML counts —
        # `execute` is typed `Result`, and only the `CursorResult` a DML really
        # returns carries the attribute.
        result = await self.db.execute(statement)
        reclaimed = int(result.rowcount or 0)  # type: ignore[attr-defined]
        if reclaimed:
            logger.warning(
                "moment_claims_reclaimed",
                count=reclaimed,
                reason="a holder stopped answering before settling",
            )
        return reclaimed

    async def expire_stale(self, *, now: datetime) -> list[str]:
        """Close the pending rows whose window has closed.

        Returns the KINDS rather than a count, for the same reason
        :meth:`insert_candidates` does: the caller counts one metric per kind,
        and ``kind="all"`` would put a value in a label the module documents as
        bounded by ``MomentKind``.

        Args:
            now: The instant the window is judged against.

        Returns:
            One entry per expired row.
        """
        statement = (
            update(ProactiveMoment)
            .where(
                ProactiveMoment.state == MomentState.PENDING.value,
                ProactiveMoment.not_after <= now,
            )
            .values(state=MomentState.EXPIRED.value, settled_at=now)
            .returning(ProactiveMoment.kind)
        )
        return [str(kind) for kind in (await self.db.execute(statement)).scalars().all()]

    async def purge_settled(self, *, before: datetime) -> int:
        """Delete settled rows older than the retention.

        This table is not a register: what LIA actually did outlives it in
        ``agent_effects`` and ``heartbeat_notifications``.

        Args:
            before: Settled strictly before this instant.

        Returns:
            How many rows were deleted.
        """
        statement = delete(ProactiveMoment).where(
            ProactiveMoment.state.in_(SETTLED_STATES),
            ProactiveMoment.settled_at.is_not(None),
            ProactiveMoment.settled_at < before,
        )
        # Counted by the server rather than by materialising every deleted id:
        # the purge runs every sweep and its result is a number.
        result = await self.db.execute(statement)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
