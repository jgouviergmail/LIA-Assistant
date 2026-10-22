"""Short, owner-fenced reads; callers end their session before any model/provider call."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.proactive_discussions.context_store.admission import (
    admissible_evidence,
    observation_key,
    reference_key,
    support_key,
)
from src.domains.proactive_discussions.context_store.checkpoints import interpretation_signature
from src.domains.proactive_discussions.context_store.filters import (
    ContextFilters,
    context_conditions,
)
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextResumeRecord,
    ContextStateRecord,
    ContextSupportRecord,
)
from src.domains.proactive_discussions.context_store.observations import changed_observations
from src.domains.proactive_discussions.context_store.pages import (
    excluded_roots,
    present_items,
    read_exclusion_page,
)
from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.context_store.restrictions import restrict_cached_topics
from src.domains.proactive_discussions.context_store.schemas import (
    ContextControls,
    ContextGeneration,
    ContextItem,
    SourceCoverage,
)
from src.domains.proactive_discussions.policy_repository import (
    DiscussionPolicyRepository,
    policy_value,
)
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SensitiveTopic,
    SourceKey,
    SourceSnapshot,
)


class ContextReader(DiscussionPolicyRepository):
    """Short owner-fenced context reads; callers end the session before any model call."""

    async def changed_inputs(
        self,
        owner_id: UUID,
        snapshots: tuple[SourceSnapshot, ...],
        *,
        allowed_sources: frozenset[SourceKey],
        allowed_topics: frozenset[SensitiveTopic],
        now: datetime,
        directives_revision: str | None = None,
        signature: str | None = None,
    ) -> tuple[DiscussionEvidence, ...]:
        """Return the admitted evidence that changed since it was last interpreted.

        Args:
            owner_id: The account.
            snapshots: The source pages this run read.
            allowed_sources: The sources the run may read.
            allowed_topics: The sensitive topics the person allowed.
            now: The current instant.
            directives_revision: The directives this interpretation runs under.
            signature: The interpretation signature, or None for the stored policy's.

        Returns:
            The evidence to interpret again.
        """
        admitted = await self.filter_inputs(
            owner_id,
            snapshots,
            allowed_sources=allowed_sources,
            allowed_topics=allowed_topics,
            now=now,
        )
        preference = await self._preference(owner_id)
        return await changed_observations(
            self.db,
            owner_id,
            admitted,
            now=now,
            signature=signature or await self.stored_signature(owner_id),
            directives_revision=directives_revision,
            context_epoch=preference.context_epoch,
        )

    async def stored_signature(self, owner_id: UUID) -> str:
        """The interpretation signature of the account's stored policy and language.

        Args:
            owner_id: The account.

        Returns:
            The signature, as a run that applies no read rule computes it.
        """
        owner = await self._owner(owner_id)
        preference = await self._preference(owner_id)
        return interpretation_signature(
            policy_value(preference, owner), normalize_language(owner.language)
        )

    async def _state(self, owner_id: UUID, *, lock: bool = False) -> ContextStateRecord:
        await self.db.execute(
            insert(ContextStateRecord)
            .values(user_id=owner_id)
            .on_conflict_do_nothing(index_elements=[ContextStateRecord.user_id])
        )
        query = select(ContextStateRecord).where(ContextStateRecord.user_id == owner_id)
        if lock:
            query = query.with_for_update()
        return (await self.db.scalars(query.execution_options(populate_existing=True))).one()

    async def controls(self, owner_id: UUID, *, roots: tuple[str, ...] = ()) -> ContextControls:
        """Read the person's controls that apply to these roots.

        Args:
            owner_id: The account.
            roots: The roots about to be read.

        Returns:
            The context epoch and generation, the last purge, the excluded roots among
            these and the versions a purge forgot.
        """
        await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        state = await self._state(owner_id)
        excluded = await excluded_roots(self.db, owner_id, roots)
        forgotten = (
            (
                await self.db.execute(
                    select(ContextResumeRecord.root, ContextResumeRecord.version).where(
                        ContextResumeRecord.user_id == owner_id, ContextResumeRecord.root.in_(roots)
                    )
                )
            )
            .tuples()
            .all()
        )
        return ContextControls(
            epoch=preference.context_epoch,
            generation=state.generation,
            forgotten_at=state.forgotten_at,
            excluded_roots=frozenset(excluded),
            forgotten_versions=dict(forgotten),
        )

    async def filter_inputs(
        self,
        owner_id: UUID,
        snapshots: tuple[SourceSnapshot, ...],
        *,
        allowed_sources: frozenset[SourceKey],
        allowed_topics: frozenset[SensitiveTopic],
        now: datetime,
        directives_revision: str | None = None,
    ) -> tuple[DiscussionEvidence, ...]:
        """Admit a run's evidence through the one admission predicate.

        Cached sensitive-topic classifications are applied first; they only restrict.

        Args:
            owner_id: The account.
            snapshots: The source pages this run read.
            allowed_sources: The sources the run may read.
            allowed_topics: The sensitive topics the person allowed.
            now: The current instant.
            directives_revision: The directives a cached classification must match,
                or None for any.

        Returns:
            The admitted evidence.

        Raises:
            ValueError: A page belongs to another account, two items share a
                reference, or more than 500 items were read.
        """
        if any(snapshot.owner_id != owner_id for snapshot in snapshots):
            raise ValueError("foreign source snapshot")
        items = tuple(item for snapshot in snapshots for item in snapshot.items)
        if len({item.reference for item in items}) != len(items):
            raise ValueError("ambiguous evidence references")
        if len(items) > 500:
            raise ValueError("context input work limit exceeded")
        roots = tuple(
            {
                root
                for item in items
                for root in (
                    observation_key(item),
                    reference_key(item.reference),
                    *(support_key(support) for support in item.supports),
                )
            }
        )
        controls = await self.controls(owner_id, roots=roots)
        items = await restrict_cached_topics(
            self.db,
            owner_id,
            items,
            now=now,
            directives_revision=directives_revision,
        )
        return tuple(
            item
            for item in items
            if admissible_evidence(
                item,
                allowed_sources=allowed_sources,
                allowed_topics=allowed_topics,
                excluded_roots=controls.excluded_roots,
                forgotten_versions=controls.forgotten_versions,
                forgotten_at=controls.forgotten_at,
                now=now,
            )
        )

    async def read_generation(
        self,
        owner_id: UUID,
        *,
        now: datetime,
        limit: int = 50,
        after_id: UUID | None = None,
        after_exclusion_id: UUID | None = None,
        filters: ContextFilters | None = None,
    ) -> ContextGeneration:
        """Return one page of the context and of the non-use choices, with exact totals.

        A page and its total come from one filtered selection (ADR-185).

        Args:
            owner_id: The account.
            now: The current instant; expired items are never listed.
            limit: The page size (1 to 100).
            after_id: The cursor of the item page.
            after_exclusion_id: The cursor of the non-use choice page.
            filters: The person's filters, or None for none.

        Returns:
            The context generation page.

        Raises:
            ValueError: The page size is outside 1..100.
        """
        if not 1 <= limit <= 100:
            raise ValueError("context page limit outside 1..100")
        controls = await self.controls(owner_id)
        state = await self._state(owner_id)
        owner = await self._owner(owner_id)
        preference = await self._preference(owner_id)
        visible = context_conditions(
            owner_id, filters or ContextFilters(), policy_value(preference, owner), now=now
        )
        query = select(ContextItemRecord).where(*visible).order_by(ContextItemRecord.id)
        if after_id is not None:
            query = query.where(ContextItemRecord.id > after_id)
        rows = (await self.db.scalars(query.limit(limit + 1))).all()
        total = await self.db.scalar(
            select(func.count()).select_from(ContextItemRecord).where(*visible)
        )
        page = await read_exclusion_page(
            self.db, owner_id, limit=limit, after_id=after_exclusion_id
        )
        return ContextGeneration(
            generation=state.generation,
            context_epoch=controls.epoch,
            forgotten_at=state.forgotten_at,
            refresh_requested=state.refresh_requested,
            items=await present_items(self.db, owner_id, list(rows[:limit])),
            total=total or 0,
            next_cursor=rows[limit - 1].id if len(rows) > limit else None,
            exclusions=page.items,
            exclusions_total=page.total,
            exclusions_next_cursor=page.next_cursor,
            coverage=tuple(SourceCoverage.model_validate(value) for value in state.coverage),
        )

    async def usable_items(
        self,
        owner_id: UUID,
        *,
        allowed_sources: frozenset[SourceKey],
        allowed_topics: frozenset[SensitiveTopic],
        verified_evidence: tuple[DiscussionEvidence, ...],
        now: datetime,
    ) -> tuple[ContextItem, ...]:
        """Return the stored items still usable on the evidence read again now.

        An item is usable when each of its proofs was read again at the same version,
        from a source still allowed, with consented topics, and the person did not
        exclude it; its proofs are refreshed from the new read.

        Args:
            owner_id: The account.
            allowed_sources: The sources the run may read.
            allowed_topics: The sensitive topics the person allowed.
            verified_evidence: The evidence read again by this run.
            now: The current instant.

        Returns:
            The usable items, most recently updated first (at most a hundred).
        """
        await self._owner(owner_id)
        verified = {observation_key(item): item for item in verified_evidence}
        support = select(ContextSupportRecord.id).where(
            ContextSupportRecord.user_id == owner_id,
            ContextSupportRecord.item_id == ContextItemRecord.id,
        )
        unsupported = support.where(ContextSupportRecord.root.not_in(tuple(verified)))
        rows = (
            await self.db.scalars(
                select(ContextItemRecord)
                .where(
                    ContextItemRecord.user_id == owner_id,
                    ContextItemRecord.expires_at > now,
                    support.exists(),
                    ~unsupported.exists(),
                )
                .order_by(ContextItemRecord.updated_at.desc(), ContextItemRecord.id)
                .limit(settings.discussion_reused_items_max)
            )
        ).all()
        candidates = await present_items(self.db, owner_id, list(rows))
        references = {item.reference: item for item in verified_evidence}
        return tuple(
            current
            for item in candidates
            if (
                current := _current_item(
                    item,
                    verified,
                    references,
                    allowed_sources=allowed_sources,
                    allowed_topics=allowed_topics,
                    now=now,
                )
            )
            is not None
        )


def _current_item(
    item: ContextItem,
    verified: dict[str, DiscussionEvidence],
    references: dict[str, DiscussionEvidence],
    *,
    allowed_sources: frozenset[SourceKey],
    allowed_topics: frozenset[SensitiveTopic],
    now: datetime,
) -> ContextItem | None:
    if item.excluded:
        return None
    facts = tuple(verified.get(proof.root) for proof in item.proofs)
    if not all(
        fact is not None and fact.version == proof.version
        for fact, proof in zip(facts, item.proofs, strict=True)
    ):
        return None
    current = tuple(fact for fact in facts if fact is not None)
    if not all(
        _permitted_now(fact, allowed_sources, allowed_topics, now)
        and set(proof.sensitive_topics) <= allowed_topics
        for fact, proof in zip(current, item.proofs, strict=True)
    ):
        return None
    return item.model_copy(
        update={
            "proofs": tuple(
                proof_of(fact, references, now=now).model_copy(
                    update={
                        "sensitive_topics": tuple(
                            sorted(set(fact.sensitive_topics) | set(previous.sensitive_topics))
                        )
                    }
                )
                for fact, previous in zip(current, item.proofs, strict=True)
            )
        }
    )


def _permitted_now(
    fact: DiscussionEvidence,
    sources: frozenset[SourceKey],
    topics: frozenset[SensitiveTopic],
    now: datetime,
) -> bool:
    return (
        fact.source in sources
        and set(fact.required_sources) <= sources
        and set(fact.sensitive_topics) <= topics
        and (fact.expires_at is None or fact.expires_at > now)
    )
