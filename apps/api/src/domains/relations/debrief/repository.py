"""Data access for ``relation_debriefs`` — the claim, and what settles it.

The interesting half is the CLAIM. Two tabs on the same relationship, or a tab
and a manual rebuild, must never spend two LLM calls; and a builder that dies
mid-flight must not wedge the row until the end of time.

Both are one statement: a conditional ``INSERT … ON CONFLICT DO UPDATE …
WHERE``, whose empty ``RETURNING`` means *somebody else owns this build, or
today's is already settled*. There is no read-then-write, so there is no window
between the two — and no ``SET NX`` followed by an unconditional release, which
is the shape the concurrency doctrine forbids.

Every settle quotes the ``claim_owner`` it was given. A builder whose lease
expired while it worked therefore writes NOTHING: the row belongs to whoever
claimed it next, and a stale writer overwriting a fresher answer is exactly
what a fencing token exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.debrief.models import DebriefState, RelationDebrief

#: States whose row is HELD by ``held_until`` — a lease in flight, or the
#: cooldown a failure left behind. Both are re-claimable once it passes.
_HELD = (DebriefState.BUILDING, DebriefState.FAILED)

#: States holding an answer. They are re-claimable only when the answer no
#: longer matches the reader's day, language or scope.
_SETTLED = (DebriefState.READY, DebriefState.EMPTY)


class RelationDebriefRepository:
    """Data access for one user's relationship debriefs."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session owned by the caller.

        Args:
            db: Async session (never shared with a concurrent task).
        """
        self.db = db

    async def get(self, user_id: UUID, name_key: str) -> RelationDebrief | None:
        """The stored debrief of one relationship, whatever its state.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.

        Returns:
            The row, or None when this relationship has never been debriefed.
        """
        result = await self.db.execute(
            select(RelationDebrief).where(
                RelationDebrief.user_id == user_id,
                RelationDebrief.name_key == name_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_injectable(self, user_id: UUID, *, not_before: date) -> list[RelationDebrief]:
        """Debriefs fresh enough to be injected into a chat turn.

        Deliberately NOT restricted to today's: the card shows a dated debrief
        and says when it was written, so hiding the same row from the chat
        would make two surfaces disagree about one relationship. The bound is
        an AGE, published by the caller, and the injected block carries it.

        Args:
            user_id: Owner.
            not_before: Oldest local date still worth injecting.

        Returns:
            Ready debriefs, newest first.
        """
        result = await self.db.execute(
            select(RelationDebrief)
            .where(
                RelationDebrief.user_id == user_id,
                RelationDebrief.state == DebriefState.READY,
                RelationDebrief.generated_for >= not_before,
            )
            .order_by(RelationDebrief.generated_for.desc(), RelationDebrief.name_key)
        )
        return list(result.scalars().all())

    async def claim(
        self,
        user_id: UUID,
        *,
        name_key: str,
        display_name: str,
        local_date: date,
        language: str,
        scope_digest: str,
        lease_seconds: int,
        force: bool = False,
        now: datetime | None = None,
    ) -> UUID | None:
        """Take ownership of today's build, atomically — or decline.

        Claimable when, and only when:

        - nothing is stored yet;
        - the caller forces a rebuild (the manual control, capped upstream);
        - a build is in flight but its lease expired (its builder died);
        - a previous build failed and its cooldown elapsed;
        - the settled row is for another day, another language, or another
          scope — the three things that make a stored text contradict the
          user's own settings.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            display_name: Spelling to render.
            local_date: The user's local date this build belongs to.
            language: Backend-canonical language to write in.
            scope_digest: Digest of the 360° scope being applied.
            lease_seconds: How long this claim is held before it goes stale.
            force: Whether this is an explicit rebuild.
            now: Injected clock (tests).

        Returns:
            The owner token to quote when settling, or None when the build
            belongs to somebody else — or is already done.
        """
        moment = now or datetime.now(UTC)
        owner = uuid4()
        values: dict[str, Any] = {
            "user_id": user_id,
            "name_key": name_key,
            "display_name": display_name,
            "generated_for": local_date,
            "language": language,
            "scope_digest": scope_digest,
            "state": DebriefState.BUILDING,
            "claim_owner": owner,
            "held_until": moment + timedelta(seconds=lease_seconds),
            "sections_used": [],
            "unavailable": [],
        }
        insert_stmt = pg_insert(RelationDebrief).values(**values)
        # `held_until` covers BOTH in-flight and failed rows: "not available
        # before this instant" is one predicate, so a crashed builder and a
        # cooled-down failure are re-claimed by the same clause.
        expired = or_(
            RelationDebrief.held_until.is_(None),
            RelationDebrief.held_until < moment,
        )
        stale_settings = or_(
            RelationDebrief.generated_for < local_date,
            RelationDebrief.language != language,
            RelationDebrief.scope_digest != scope_digest,
        )
        claimable = or_(
            # A build nobody is finishing: dead builder, or a cooled-down failure.
            and_(RelationDebrief.state.in_(_HELD), expired),
            # A settled answer that no longer matches the reader's own settings.
            and_(RelationDebrief.state.in_(_SETTLED), stale_settings),
        )
        statement = insert_stmt.on_conflict_do_update(
            constraint="uq_relation_debriefs_user_name",
            set_={
                "display_name": insert_stmt.excluded.display_name,
                "generated_for": insert_stmt.excluded.generated_for,
                "language": insert_stmt.excluded.language,
                "scope_digest": insert_stmt.excluded.scope_digest,
                "state": insert_stmt.excluded.state,
                "claim_owner": insert_stmt.excluded.claim_owner,
                "held_until": insert_stmt.excluded.held_until,
                "updated_at": moment,
            },
            # A forced rebuild still writes through the SAME statement: the
            # control is capped upstream, and a second code path would be a
            # second set of claim semantics to keep in step.
            where=None if force else claimable,
        ).returning(RelationDebrief.claim_owner)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def _settle(self, user_id: UUID, name_key: str, owner: UUID, **values: Any) -> bool:
        """Write a terminal state onto a row we still own, or write nothing.

        The ``claim_owner`` condition is the fencing token: a builder whose
        lease expired while it worked must not overwrite the answer somebody
        else has since produced. Every settle also RELEASES the claim, so the
        three public wrappers never have to remember to.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            owner: The token :meth:`claim` returned.
            **values: Columns this particular outcome writes — and only those.
                A column absent here keeps whatever it held, which is what
                lets a failed rebuild leave the previous answer standing.

        Returns:
            True when the row was ours and was written.
        """
        result = await self.db.execute(
            update(RelationDebrief)
            .where(
                RelationDebrief.user_id == user_id,
                RelationDebrief.name_key == name_key,
                RelationDebrief.claim_owner == owner,
            )
            .values(claim_owner=None, updated_at=datetime.now(UTC), **values)
        )
        return bool(getattr(result, "rowcount", 0))

    async def settle_ready(
        self,
        user_id: UUID,
        *,
        name_key: str,
        owner: UUID,
        display_name: str,
        body: dict[str, Any],
        usage: dict[str, Any] | None,
        evidence_digest: str,
        sections_used: list[str],
        unavailable: list[str],
        generated_at: datetime,
    ) -> bool:
        """Store a debrief that was written.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            owner: The token :meth:`claim` returned.
            display_name: The spelling to render — the CANONICAL one the card
                resolved, not the one the request happened to carry. Two
                surfaces naming the same person differently is how a chat block
                comes to greet somebody by a phone number.
            body: The structured payload.
            usage: What the call cost — stored beside the words it paid for, so
                the two can never describe different builds. A failure keeps
                both; an emptied relationship clears both.
            evidence_digest: Digest of what the model was shown.
            sections_used: Sections the debrief actually read.
            unavailable: Sections asked for that could not be read.
            generated_at: When the body was produced.

        Returns:
            True when the row was ours and was written.
        """
        return await self._settle(
            user_id,
            name_key,
            owner,
            state=DebriefState.READY,
            display_name=display_name,
            body=body,
            usage=usage,
            evidence_digest=evidence_digest,
            sections_used=sections_used,
            unavailable=unavailable,
            generated_at=generated_at,
            held_until=None,
        )

    async def settle_empty(
        self,
        user_id: UUID,
        *,
        name_key: str,
        owner: UUID,
        sections_used: list[str],
        unavailable: list[str],
    ) -> bool:
        """Record that there was nothing to synthesise.

        The body IS cleared here, unlike on a failure: a relationship that has
        become empty — every commitment closed, every message gone — is one
        whose old debrief describes data that no longer exists.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            owner: The token :meth:`claim` returned.
            sections_used: Sections that were looked at.
            unavailable: Sections asked for that could not be read.

        Returns:
            True when the row was ours and was written.
        """
        return await self._settle(
            user_id,
            name_key,
            owner,
            state=DebriefState.EMPTY,
            body=None,
            usage=None,
            evidence_digest=None,
            generated_at=None,
            sections_used=sections_used,
            unavailable=unavailable,
            held_until=None,
        )

    async def settle_failed(
        self, user_id: UUID, *, name_key: str, owner: UUID, held_until: datetime
    ) -> bool:
        """Record a build that did not produce a debrief — and keep the old one.

        Nothing else is written. A rebuild that fails must leave the previous
        answer standing: replacing a debrief the reader could still use with an
        empty panel turns "I could not refresh this" into "there is nothing",
        which is the same lie ADR-184 forbids one layer up.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            owner: The token :meth:`claim` returned.
            held_until: Cooldown before a retry may be claimed.

        Returns:
            True when the row was ours and was written.
        """
        return await self._settle(
            user_id,
            name_key,
            owner,
            state=DebriefState.FAILED,
            held_until=held_until,
        )

    async def carry_forward(
        self,
        user_id: UUID,
        *,
        name_key: str,
        owner: UUID,
        local_date: date,
        state: DebriefState,
    ) -> bool:
        """Carry an unchanged debrief into today without rewriting it.

        A rebuild whose evidence digest is identical produced no new text, so
        ``generated_at`` must NOT move — it states when the words were written,
        and bumping it would claim a freshness nothing earned. The DAY moves,
        because the reader did ask and the answer WAS verified at that moment.

        The state is carried too, not forced: an empty relationship that is
        still empty stays empty, and turning it into ``ready`` would promise a
        body that was never written.

        Args:
            user_id: Owner.
            name_key: Canonical folded identity.
            owner: The token :meth:`claim` returned.
            local_date: The user's local date this build belongs to.
            state: The state the row held before the rebuild.

        Returns:
            True when the row was ours and was written.
        """
        return await self._settle(
            user_id,
            name_key,
            owner,
            state=state,
            generated_for=local_date,
            held_until=None,
        )

    async def delete_for_keys(self, user_id: UUID, name_keys: list[str]) -> int:
        """Drop the debriefs of identities that no longer exist as such.

        A merge and a split both change which rows belong to whom, and a
        debrief keyed on the old identity would describe a person the CRM no
        longer has. Deleting is the only honest repair: the next card open
        rebuilds one for the identity that DOES exist.

        Args:
            user_id: Owner.
            name_keys: Canonical keys to drop (blank entries ignored).

        Returns:
            How many rows were removed.
        """
        keys = [key for key in name_keys if key]
        if not keys:
            return 0
        result = await self.db.execute(
            delete(RelationDebrief).where(
                RelationDebrief.user_id == user_id,
                RelationDebrief.name_key.in_(keys),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)
