"""Atomic publication of validated deltas; stale workers cannot resurrect purged context."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select

from src.core.exceptions import ResourceConflictError
from src.domains.proactive_discussions.context_store.admission import reference_key
from src.domains.proactive_discussions.context_store.commands import ContextCommands
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextSupportRecord,
)
from src.domains.proactive_discussions.context_store.observations import apply_observations
from src.domains.proactive_discussions.context_store.preparation import (
    prepare_items,
    same_meaning,
)
from src.domains.proactive_discussions.context_store.schemas import (
    ContextCandidate,
    ContextGeneration,
    ContextItem,
    ProposalRefusal,
    SourceCoverage,
)
from src.domains.proactive_discussions.policy_repository import policy_value
from src.domains.proactive_discussions.repository import owns_claim
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SensitiveTopic,
    SourceKey,
    SourceSnapshot,
)


@dataclass(frozen=True, slots=True)
class PublishedGeneration:
    """What one publication left: the generation after it, and what it set aside.

    Attributes:
        generation: The context generation after publication.
        refused: Why each proposal it could not admit was set aside.
        changed: Whether the publication moved the generation (a checkpoint or
            an item changed): the context was updated.
    """

    generation: ContextGeneration
    refused: Counter[ProposalRefusal]
    changed: bool = False


class ContextUpdater(ContextCommands):
    """Publish a context generation: observations and items together, under the epoch."""

    async def publish_generation(
        self,
        owner_id: UUID,
        candidate: ContextCandidate,
        *,
        snapshots: tuple[SourceSnapshot, ...],
        allowed_sources: frozenset[SourceKey],
        allowed_topics: frozenset[SensitiveTopic],
        now: datetime,
        claim: RunClaim | None = None,
        directives_revision: str | None = None,
        analysed_references: frozenset[str] | None = None,
        signature: str | None = None,
    ) -> PublishedGeneration:
        """Publish a context candidate as the next generation.

        The candidate must rest on the current policy revision, context epoch and
        generation, and a run must still hold its claim, so a stale worker never
        resurrects purged context. Inputs are admitted again, observations
        checkpointed and items written; the generation moves only when something
        changed. A rebuild request is left as it is: only the rebuild's own end
        clears it (``complete_refresh``), so one cut short resumes. Each proposal is
        prepared on its own: one its evidence cannot carry is set aside and counted,
        never the whole candidate (``prepare_items``).

        Args:
            owner_id: The account.
            candidate: The validated proposals and the versions they rest on.
            snapshots: The source pages the candidate was built from.
            allowed_sources: The sources the run may read.
            allowed_topics: The sensitive topics the person allowed.
            now: The current instant.
            claim: The run's claim, when a run publishes.
            directives_revision: The directives the interpretation ran under.
            analysed_references: The evidence actually interpreted, when not all.
            signature: The interpretation signature its checkpoints record, or None
                for the stored policy's.

        Returns:
            The context generation after publication, and why each proposal it could
            not admit was set aside.

        Raises:
            ResourceConflictError: The candidate or the claim is stale.
        """
        owner = await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        state = await self._state(owner_id, lock=True)
        if (
            candidate.policy_revision != preference.revision
            or candidate.context_epoch != preference.context_epoch
            or candidate.base_generation != state.generation
        ):
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        if claim is not None and not owns_claim(preference, claim, now):
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_CLAIM"})
        admitted = await self.filter_inputs(
            owner_id,
            snapshots,
            allowed_sources=allowed_sources,
            allowed_topics=allowed_topics,
            now=now,
            directives_revision=directives_revision,
        )
        references = {item.reference: item for item in admitted}
        prepared, refused = prepare_items(
            owner_id,
            candidate.proposals,
            references,
            allowed_topics=allowed_topics,
            generation=state.generation + 1,
            now=now,
            coverage=snapshots,
            timezone=policy_value(preference, owner).timezone,
        )
        observed = _analysis_slice(admitted, analysed_references)
        changed = await apply_observations(
            self.db,
            owner_id,
            observed,
            now=now,
            policy_revision=candidate.policy_revision,
            directives_revision=directives_revision,
            context_epoch=candidate.context_epoch,
            signature=signature or await self.stored_signature(owner_id),
        )
        for item in prepared:
            changed = await self._put_item(owner_id, item) or changed
        if changed:
            state.generation += 1
        state.coverage = latest_coverage(state.coverage, snapshots)
        # The rebuild request outlives each pass's publication: only a rebuild that
        # reached its end clears it, so one cut short is served again and resumes.
        await self.db.flush()
        return PublishedGeneration(
            await self.read_generation(owner_id, now=now), refused, changed=changed
        )

    async def _put_item(self, owner_id: UUID, item: ContextItem) -> bool:
        row = await self.db.scalar(
            select(ContextItemRecord).where(
                ContextItemRecord.user_id == owner_id, ContextItemRecord.id == item.id
            )
        )
        if row is not None and same_meaning(ContextItem.model_validate(row.data), item):
            item = item.model_copy(update={"revision": row.revision, "generation": row.generation})
            row.data = item.model_dump(mode="json")
            row.expires_at = min(proof.expires_at for proof in item.proofs)
            return False
        revision = row.revision + 1 if row is not None else 1
        item = item.model_copy(update={"revision": revision})
        if row is None:
            row = ContextItemRecord(id=item.id, user_id=owner_id)
            self.db.add(row)
        row.kind, row.revision, row.generation = item.kind, item.revision, item.generation
        row.data = item.model_dump(mode="json")
        row.root_keys = sorted(
            {
                root
                for proof in item.proofs
                for root in (proof.root, reference_key(proof.reference), *proof.support_roots)
            }
        )
        row.expires_at = min(proof.expires_at for proof in item.proofs)
        await self.db.flush()
        await self.db.execute(
            delete(ContextSupportRecord).where(
                ContextSupportRecord.user_id == owner_id, ContextSupportRecord.item_id == item.id
            )
        )
        self.db.add_all(
            [
                ContextSupportRecord(user_id=owner_id, item_id=item.id, root=proof.root)
                for proof in item.proofs
            ]
        )
        await self.db.flush()
        return True


def latest_coverage(
    previous: list[dict[str, object]], snapshots: tuple[SourceSnapshot, ...]
) -> list[dict[str, object]]:
    """Each source's latest read window, replacing the previous one for the sources read.

    This is latest-read coverage, never the union of pages presented as a complete
    history.

    Args:
        previous: The stored coverage.
        snapshots: The pages read now.

    Returns:
        The coverage to store, one entry per source, sorted by source.
    """
    latest = {
        value.source: value for value in (SourceCoverage.model_validate(row) for row in previous)
    }
    for snapshot in snapshots:
        latest[snapshot.source] = SourceCoverage(
            source=snapshot.source,
            start=snapshot.window_start,
            end=snapshot.window_end,
            read_at=snapshot.read_at,
            status=snapshot.status,
            kind=snapshot.coverage_kind,
            complete=snapshot.complete,
            cursor=snapshot.cursor,
            revision=snapshot.revision,
        )
    return [value.model_dump(mode="json") for _, value in sorted(latest.items())]


def _analysis_slice(
    items: tuple[DiscussionEvidence, ...], references: frozenset[str] | None
) -> tuple[DiscussionEvidence, ...]:
    if references is None:
        return items
    return tuple(item for item in items if item.reference in references)
