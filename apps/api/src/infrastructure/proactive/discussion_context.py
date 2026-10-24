"""Short native context transactions around an otherwise session-free model loop."""

from datetime import UTC, datetime
from uuid import UUID

import structlog

from src.core.exceptions import ResourceConflictError
from src.domains.proactive_discussions.context_store.candidates import pending_proofs
from src.domains.proactive_discussions.context_store.checkpoints import (
    ReadyCheckpoint,
    interpretation_signature,
    readiness_signature,
    verified_ready,
)
from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.context_store.observations import (
    apply_observations,
    changed_observations,
)
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.schemas import (
    ContextCandidate,
    ContextEvidenceLink,
    ContextItem,
    ContextProposal,
)
from src.domains.proactive_discussions.context_store.updater import latest_coverage
from src.domains.proactive_discussions.contextualization.loop import ContextPublication
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.repository import owns_claim
from src.domains.proactive_discussions.rule_controls import RuleCache
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


class NativeContextStore:
    """The context store the loop runs on: one short session per operation.

    Every write is fenced by the run's claim, so a run that lost the account
    writes nothing.
    """

    def __init__(
        self,
        claim: RunClaim,
        policy: DiscussionPolicy,
        directives_revision: str,
        language: str,
    ) -> None:
        self.claim, self.policy, self.directives_revision = claim, policy, directives_revision
        self.language = language
        self.sources = effective_sources(policy, frozenset(SourceKey))
        self.topics = frozenset(policy.sensitive_topics)

    @property
    def signature(self) -> str:
        """What this run's interpretation depends on (its sources narrowed by the rules)."""
        return interpretation_signature(self.policy, self.language)

    @property
    def owner(self) -> UUID:
        """The account the run serves."""
        return self.claim.owner_id

    async def proof_candidates(self) -> tuple[ContextEvidenceLink, ...]:
        """Return the stored proofs to read again before the context is reused."""
        async with get_db_context() as db:
            return await pending_proofs(
                db, self.owner, sources=self.sources, topics=self.topics, now=datetime.now(UTC)
            )

    async def admit(self, snapshots: tuple[SourceSnapshot, ...]) -> tuple[DiscussionEvidence, ...]:
        """Admit the evidence of a run's pages through the person's controls."""
        async with get_db_context() as db:
            return await ContextRepository(db).filter_inputs(
                self.owner,
                snapshots,
                allowed_sources=self.sources,
                allowed_topics=self.topics,
                now=datetime.now(UTC),
                directives_revision=self.directives_revision,
            )

    async def changed(
        self, facts: tuple[DiscussionEvidence, ...]
    ) -> tuple[DiscussionEvidence, ...]:
        """Return the facts whose interpretation checkpoint differs from this run's.

        A rebuild moved the context epoch, so on its first pass every fact differs;
        each pass then checkpoints what it analysed and the next one offers the rest
        (returning every fact while the rebuild ran had each pass re-offer the same
        first facts, measured on production 2026-10-21). An interrupted rebuild
        resumes where it stopped instead of paying again.
        """
        async with get_db_context() as db:
            return await changed_observations(
                db,
                self.owner,
                facts,
                now=datetime.now(UTC),
                signature=self.signature,
                directives_revision=self.directives_revision,
                context_epoch=self.claim.context_epoch,
            )

    async def read_rule_cache(self) -> RuleCache | None:
        """Return the compiled read restriction cached for this account, if any."""
        async with get_db_context() as db:
            state = await ContextRepository(db)._state(self.owner)
            return RuleCache.model_validate(state.rule_cache) if state.rule_cache else None

    async def save_rule_cache(self, cache: RuleCache) -> None:
        """Cache a compiled read restriction, while the run still holds its claim.

        Raises:
            ResourceConflictError: The claim was lost.
        """
        async with get_db_context() as db:
            state = await self._fenced_state(ContextRepository(db))
            state.rule_cache = cache.stored()

    async def _fenced_state(self, repo: ContextRepository) -> ContextStateRecord:
        await repo._owner(self.owner)
        pref = await repo._preference(self.owner, lock=True)
        if not owns_claim(pref, self.claim, datetime.now(UTC)):
            raise ResourceConflictError("discussion_context")
        return await repo._state(self.owner, lock=True)

    async def record_coverage(self, snapshots: tuple[SourceSnapshot, ...]) -> None:
        """Record what the run read, even when it published nothing, while it holds its claim.

        The settings page then shows what the latest run covered, source by source.
        A run that lost its claim writes nothing here and is not stopped here: the
        coverage is informative, and the run's next authority check stops it with
        its own reason.

        Args:
            snapshots: The pages the run read.
        """
        if not snapshots:
            return
        async with get_db_context() as db:
            repo = ContextRepository(db)
            await repo._owner(self.owner)
            preference = await repo._preference(self.owner, lock=True)
            if not owns_claim(preference, self.claim, datetime.now(UTC)):
                return
            state = await repo._state(self.owner, lock=True)
            state.coverage = latest_coverage(state.coverage, snapshots)

    async def complete_refresh(self) -> None:
        """Clear the rebuild request, while the run still holds its claim.

        Raises:
            ResourceConflictError: The claim was lost.
        """
        async with get_db_context() as db:
            state = await self._fenced_state(ContextRepository(db))
            state.refresh_requested = False

    def _readiness_signature(self) -> str:
        return readiness_signature(
            self.signature, self.claim.context_epoch, self.directives_revision
        )

    async def ready_references(self, facts: tuple[DiscussionEvidence, ...]) -> set[str]:
        """Return the stored ready context's references, if it still holds on these facts.

        Nothing is returned while a rebuild is requested.
        """
        async with get_db_context() as db:
            state = await ContextRepository(db)._state(self.owner)
            if not state.ready_context or state.refresh_requested:
                return set()
            return verified_ready(
                ReadyCheckpoint.model_validate(state.ready_context),
                self._readiness_signature(),
                facts,
            )

    async def remember_ready(self, facts: tuple[DiscussionEvidence, ...]) -> None:
        """Store these facts' versions as the ready context, while the claim holds.

        Raises:
            ResourceConflictError: The claim was lost.
        """
        async with get_db_context() as db:
            state = await self._fenced_state(ContextRepository(db))
            state.ready_context = ReadyCheckpoint(
                signature=self._readiness_signature(),
                references={fact.reference: fact.version for fact in facts},
            ).model_dump(mode="json")

    async def warm(self, facts: tuple[DiscussionEvidence, ...]) -> tuple[ContextItem, ...]:
        """Return the stored items still usable on these facts."""
        async with get_db_context() as db:
            return await ContextRepository(db).usable_items(
                self.owner,
                allowed_sources=self.sources,
                allowed_topics=self.topics,
                verified_evidence=facts,
                now=datetime.now(UTC),
            )

    async def publish(
        self,
        proposals: tuple[ContextProposal, ...],
        analysed: tuple[DiscussionEvidence, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> ContextPublication:
        """Publish the context call's proposals as the next generation; return what it left.

        Only the facts the call analysed become interpretation checkpoints, their topic
        classifications included, so a refused topic is remembered as a restriction;
        coverage stays the native pages. The ready context is cleared. A proposal its
        evidence cannot carry is set aside alone and logged by reason, never the
        generation.

        Args:
            proposals: The proposals the call returned, within the person's controls.
            analysed: The facts the call classified.
            snapshots: The pages read.

        Returns:
            The items usable on the analysed facts, why each proposal the
            publication could not admit was set aside, and whether it moved the
            context's generation.

        Raises:
            ResourceConflictError: The context or the claim is stale.
        """
        classified = {item.reference: item for item in analysed}
        # Only offered facts become interpretation checkpoints. Coverage remains
        # the actual native page; a truncated projection cannot prove absence.
        offered = tuple(
            page.model_copy(
                update={"items": tuple(classified.get(item.reference, item) for item in page.items)}
            )
            for page in snapshots
        )
        async with get_db_context() as db:
            repo = ContextRepository(db)
            state = await repo.read_generation(self.owner, now=datetime.now(UTC), limit=1)
            candidate = ContextCandidate(
                policy_revision=self.claim.policy_revision,
                context_epoch=self.claim.context_epoch,
                base_generation=state.generation,
                proposals=proposals,
            )
            published = await repo.publish_generation(
                self.owner,
                candidate,
                snapshots=offered,
                allowed_sources=self.sources,
                allowed_topics=self.topics,
                now=datetime.now(UTC),
                claim=self.claim,
                directives_revision=self.directives_revision,
                analysed_references=frozenset(classified),
                signature=self.signature,
            )
            (await repo._state(self.owner)).ready_context = None
            # Cache rejected-topic classifications as body-free restrictions too.
            await apply_observations(
                db,
                self.owner,
                analysed,
                now=datetime.now(UTC),
                policy_revision=self.policy.revision,
                directives_revision=self.directives_revision,
                context_epoch=self.claim.context_epoch,
                signature=self.signature,
            )
        if published.refused:
            logger.info(
                "discussion_context_proposals_refused",
                user_id=str(self.owner),
                run_id=str(self.claim.run_id),
                stage="publication",
                refused=dict(sorted(published.refused.items())),
            )
        return ContextPublication(
            await self.warm(analysed), published.refused, changed=published.changed
        )
