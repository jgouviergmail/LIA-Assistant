"""Reading what is pending, and appending to a chain (ADR-263, lot 5).

Every statement here is shaped by a measurement rather than a habit.

**Finding the pending set** goes through PARTIAL indexes led by ``user_id``:
measured on 50 000 rows, a join against the chain costs 9,93 ms per tick and
grows with the register, while ``WHERE notarised_at IS NULL`` costs 0,64 ms and
grows with the PENDING set alone. Leading by ``user_id`` lets one index answer
both « which accounts have work » and « that account's work, in order ».

**A NULL marker rather than a timestamp watermark** — because a watermark
misses a row whose transaction committed after the notary passed. Simulated: 0
notarised during the open transaction, 1 on the next pass, nothing left behind.
That false negative is exactly the kind an audit device must not have.

**One transaction per account**, so a chain that cannot be appended does not
hold up every other account's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.chain_digest import DIGEST_VERSION, row_digest
from src.domains.agents.effects.chain_link import ChainLink, link_hash
from src.domains.agents.effects.chain_spec import (
    CHAIN_SUBJECTS,
    EFFECT_CLAIMED,
    EFFECT_SETTLED,
    GENESIS_KIND,
    TREATMENT_RECORDED,
    ChainSubject,
    digest_of,
)
from src.domains.agents.effects.models import (
    AgentEffect,
    AgentTreatment,
    EffectStatus,
    LedgerChainEntry,
)


@dataclass(frozen=True)
class PendingItem:
    """One register row waiting to enter a chain.

    Attributes:
        subject: Which stage covers it.
        subject_id: The register row.
        when: The row's own moment, used to interleave the three stages
            chronologically — the order a reader expects.
        digest: The digest of the columns that stage covers.
    """

    subject: ChainSubject
    subject_id: uuid.UUID
    when: datetime
    digest: str


@dataclass(frozen=True)
class ChainHead:
    """Where an account's chain currently ends.

    Attributes:
        seq: Last position; 0 when the chain does not exist yet, which is what
            makes the next entry a genesis.
        entry_hash: Its hash — the next link's predecessor, and the value an
            operator writes down to detect a later rewrite of the whole chain.
        occurred_at: When it was appended. This is what a surface shows as
            « sealed up to »: claiming more would be claiming coverage the
            asynchronous notary has not given yet.
    """

    seq: int = 0
    entry_hash: str | None = None
    occurred_at: datetime | None = None


class ChainRepository:
    """Persistence for the tamper-evident chain."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the session this repository works through.

        Args:
            db: The session, owned by the caller.
        """
        self.db = db

    async def accounts_with_pending(self, *, limit: int) -> list[uuid.UUID]:
        """Accounts holding at least one un-notarised row.

        Args:
            limit: How many accounts one pass may serve.

        Returns:
            Their ids. Ordered, so a backlog is worked through predictably
            rather than by whichever account the planner happened to reach.
        """
        claimed = select(AgentEffect.user_id).where(AgentEffect.notarised_at.is_(None))
        settled = select(AgentEffect.user_id).where(
            AgentEffect.settled_notarised_at.is_(None),
            AgentEffect.status != EffectStatus.CLAIMED,
        )
        recorded = select(AgentTreatment.user_id).where(AgentTreatment.notarised_at.is_(None))
        union = claimed.union(settled, recorded).subquery()
        rows = await self.db.execute(select(union.c.user_id).order_by(union.c.user_id).limit(limit))
        return list(rows.scalars().all())

    async def pending_for(self, user_id: uuid.UUID, *, limit: int) -> list[PendingItem]:
        """One account's pending rows, oldest first, across the three stages.

        Args:
            user_id: Whose chain.
            limit: Ceiling for this pass; a backlog is worked in slices rather
                than in one transaction that could run for minutes.

        Returns:
            The items, interleaved by their own timestamps. The tie-break is
            the row id, so two rows sharing a timestamp are ordered the same
            way on every pass — a chain must not depend on the planner.
        """
        items: list[PendingItem] = []

        claims = await self.db.execute(
            select(AgentEffect)
            .where(AgentEffect.user_id == user_id, AgentEffect.notarised_at.is_(None))
            .order_by(AgentEffect.claimed_at, AgentEffect.id)
            .limit(limit)
        )
        for effect in claims.scalars().all():
            items.append(
                PendingItem(
                    subject=EFFECT_CLAIMED,
                    subject_id=effect.id,
                    when=effect.claimed_at,
                    digest=digest_of(effect, EFFECT_CLAIMED),
                )
            )

        settlements = await self.db.execute(
            select(AgentEffect)
            .where(
                AgentEffect.user_id == user_id,
                AgentEffect.settled_notarised_at.is_(None),
                AgentEffect.status != EffectStatus.CLAIMED,
            )
            .order_by(AgentEffect.closed_at, AgentEffect.id)
            .limit(limit)
        )
        for effect in settlements.scalars().all():
            items.append(
                PendingItem(
                    subject=EFFECT_SETTLED,
                    subject_id=effect.id,
                    # A refusal is inserted already closed, so `closed_at` is
                    # always set on a row that left `claimed`; the claim time
                    # is the honest fallback if it ever were not.
                    when=effect.closed_at or effect.claimed_at,
                    digest=digest_of(effect, EFFECT_SETTLED),
                )
            )

        treatments = await self.db.execute(
            select(AgentTreatment)
            .where(
                AgentTreatment.user_id == user_id,
                AgentTreatment.notarised_at.is_(None),
            )
            .order_by(AgentTreatment.occurred_at, AgentTreatment.id)
            .limit(limit)
        )
        for treatment in treatments.scalars().all():
            items.append(
                PendingItem(
                    subject=TREATMENT_RECORDED,
                    subject_id=treatment.id,
                    when=treatment.occurred_at,
                    digest=digest_of(treatment, TREATMENT_RECORDED),
                )
            )

        items.sort(key=lambda item: (item.when, str(item.subject_id), item.subject.kind))
        return items[:limit]

    async def head(self, user_id: uuid.UUID) -> ChainHead:
        """Where the account's chain currently ends.

        Args:
            user_id: Whose chain.

        Returns:
            The head, or an empty one when the chain does not exist yet.
        """
        row = (
            await self.db.execute(
                select(
                    LedgerChainEntry.seq,
                    LedgerChainEntry.entry_hash,
                    LedgerChainEntry.occurred_at,
                )
                .where(LedgerChainEntry.user_id == user_id)
                .order_by(LedgerChainEntry.seq.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return ChainHead()
        return ChainHead(seq=int(row[0]), entry_hash=str(row[1]), occurred_at=row[2])

    async def append(
        self,
        user_id: uuid.UUID,
        *,
        seq: int,
        kind: str,
        subject_id: uuid.UUID | None,
        payload_digest: str,
        prev_hash: str | None,
    ) -> str:
        """Add one link, and return its hash.

        The ``UNIQUE (user_id, seq)`` constraint is what makes a forked chain
        impossible: two notaries appending at once cannot both win, and the
        loser's pass simply redoes the work.

        Args:
            user_id: Whose chain.
            seq: Position, one past the head.
            kind: The stage covered.
            subject_id: The row covered, or None for the genesis.
            payload_digest: Digest of that row's covered columns.
            prev_hash: The head's hash, or None for the first entry.

        Returns:
            The new entry's hash — the next link's predecessor.
        """
        entry_hash = link_hash(
            seq=seq,
            kind=kind,
            subject_id=subject_id,
            payload_digest=payload_digest,
            prev_hash=prev_hash,
        )
        self.db.add(
            LedgerChainEntry(
                user_id=user_id,
                seq=seq,
                kind=kind,
                subject_id=subject_id,
                payload_digest=payload_digest,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                digest_version=DIGEST_VERSION,
                occurred_at=datetime.now(UTC),
            )
        )
        return entry_hash

    async def mark_notarised(self, items: list[PendingItem]) -> None:
        """Record that these rows entered the chain.

        Args:
            items: What was appended in this pass.
        """
        now = datetime.now(UTC)
        by_marker: dict[tuple[str, str], list[uuid.UUID]] = {}
        for item in items:
            key = (item.subject.model, item.subject.marker)
            by_marker.setdefault(key, []).append(item.subject_id)

        for (model_name, marker), ids in by_marker.items():
            model = AgentEffect if model_name == "AgentEffect" else AgentTreatment
            await self.db.execute(update(model).where(model.id.in_(ids)).values(**{marker: now}))

    async def accounts_with_chain(self, *, limit: int) -> list[uuid.UUID]:
        """Accounts that hold a chain at all.

        Args:
            limit: Ceiling for one sweep — an instance-wide deep walk is a
                batch job, never an HTTP request.

        Returns:
            Their ids, ordered so a sweep is reproducible.
        """
        rows = await self.db.execute(
            select(LedgerChainEntry.user_id)
            .distinct()
            .order_by(LedgerChainEntry.user_id)
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def count_accounts_with_chain(self) -> int:
        """How many accounts hold a chain, EXACTLY.

        Read from an aggregate over the whole set, never from the length of a
        capped page: a sweep that verified fifty accounts must be able to say
        fifty of how many (ADR-185).

        Returns:
            The count.
        """
        return int(
            (
                await self.db.execute(select(func.count(func.distinct(LedgerChainEntry.user_id))))
            ).scalar_one()
        )

    async def entry_count(self, user_id: uuid.UUID) -> int:
        """How many links the account's chain holds.

        Compared against the head position on every pass: a contiguous chain
        has as many entries as its last position, so a DELETED entry shows up
        here for the price of one index-only scan. It is the cheapest of the
        three tampering detections, and the only one that runs continuously.

        Args:
            user_id: Whose chain.

        Returns:
            The count.
        """
        return int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(LedgerChainEntry)
                    .where(LedgerChainEntry.user_id == user_id)
                )
            ).scalar_one()
        )

    async def oldest_pending_at(self) -> datetime | None:
        """When the oldest un-notarised row was written, across all accounts.

        Returns:
            Its moment, or None when nothing is pending. The gauge derived
            from it publishes the width of the window in which a rewrite would
            leave no trace — the design's one concession, measured rather than
            asserted.
        """
        candidates: list[Select[Any]] = [
            select(func.min(AgentEffect.claimed_at)).where(AgentEffect.notarised_at.is_(None)),
            select(func.min(AgentEffect.closed_at)).where(
                AgentEffect.settled_notarised_at.is_(None),
                AgentEffect.status != EffectStatus.CLAIMED,
            ),
            select(func.min(AgentTreatment.occurred_at)).where(
                AgentTreatment.notarised_at.is_(None)
            ),
        ]
        moments = [
            moment
            for moment in [
                (await self.db.execute(statement)).scalar_one_or_none() for statement in candidates
            ]
            if moment is not None
        ]
        return min(moments) if moments else None

    async def register_rows(self, user_id: uuid.UUID) -> int:
        """How many register rows the account holds, right now.

        Read once per account, when its chain is opened, so the genesis entry
        can state how many rows predate the chain. A retroactively notarised
        row attests to its state at chain opening, not at creation — a reader
        is entitled to know how many of them there are rather than to assume
        the chain covered every row from the start.

        Args:
            user_id: Whose registers.

        Returns:
            Actions plus consultations.
        """
        effects = (
            await self.db.execute(
                select(func.count()).select_from(AgentEffect).where(AgentEffect.user_id == user_id)
            )
        ).scalar_one()
        treatments = (
            await self.db.execute(
                select(func.count())
                .select_from(AgentTreatment)
                .where(AgentTreatment.user_id == user_id)
            )
        ).scalar_one()
        return int(effects) + int(treatments)

    async def links_for(self, user_id: uuid.UUID, *, after_seq: int, limit: int) -> list[ChainLink]:
        """One page of a chain, in order, for verification.

        Args:
            user_id: Whose chain.
            after_seq: Resume point; 0 starts at the beginning.
            limit: Page size — verification walks with bounded memory.

        Returns:
            The links.
        """
        rows = await self.db.execute(
            select(LedgerChainEntry)
            .where(LedgerChainEntry.user_id == user_id, LedgerChainEntry.seq > after_seq)
            .order_by(LedgerChainEntry.seq)
            .limit(limit)
        )
        return [
            ChainLink(
                seq=entry.seq,
                kind=entry.kind,
                subject_id=entry.subject_id,
                payload_digest=entry.payload_digest,
                prev_hash=entry.prev_hash,
                entry_hash=entry.entry_hash,
                digest_version=entry.digest_version,
                occurred_at=entry.occurred_at,
            )
            for entry in rows.scalars().all()
        ]

    async def counts(self, user_id: uuid.UUID | None = None) -> tuple[int, int]:
        """How much is chained, and how much is waiting.

        Args:
            user_id: Narrow to one account, or None for the whole instance —
                one implementation, so an operator's gauge and a user's own
                « not sealed yet » figure can never disagree.

        Returns:
            ``(entries, pending)``.
        """

        def _scope(statement: Any, column: Any) -> Any:
            return statement if user_id is None else statement.where(column == user_id)

        entries = (
            await self.db.execute(
                _scope(
                    select(func.count()).select_from(LedgerChainEntry),
                    LedgerChainEntry.user_id,
                )
            )
        ).scalar_one()
        claimed = (
            await self.db.execute(
                _scope(
                    select(func.count())
                    .select_from(AgentEffect)
                    .where(AgentEffect.notarised_at.is_(None)),
                    AgentEffect.user_id,
                )
            )
        ).scalar_one()
        settled = (
            await self.db.execute(
                _scope(
                    select(func.count())
                    .select_from(AgentEffect)
                    .where(
                        AgentEffect.settled_notarised_at.is_(None),
                        AgentEffect.status != EffectStatus.CLAIMED,
                    ),
                    AgentEffect.user_id,
                )
            )
        ).scalar_one()
        recorded = (
            await self.db.execute(
                _scope(
                    select(func.count())
                    .select_from(AgentTreatment)
                    .where(AgentTreatment.notarised_at.is_(None)),
                    AgentTreatment.user_id,
                )
            )
        ).scalar_one()
        return int(entries), int(claimed) + int(settled) + int(recorded)


def genesis_digest(user_id: uuid.UUID, *, uncovered: int) -> str:
    """The genesis entry's digest — a statement, not a covered row.

    It says, in the chain itself, that the account's history begins here and
    how many rows predate it. The honest alternative to a silence that would
    let a reader assume everything was notarised.

    Args:
        user_id: Whose chain begins.
        uncovered: Rows that already existed when the chain was opened.

    Returns:
        The digest.
    """
    return row_digest({"chain_of": user_id, "kind": GENESIS_KIND, "pre_existing_rows": uncovered})


__all__ = [
    "CHAIN_SUBJECTS",
    "ChainHead",
    "ChainRepository",
    "PendingItem",
    "genesis_digest",
]
