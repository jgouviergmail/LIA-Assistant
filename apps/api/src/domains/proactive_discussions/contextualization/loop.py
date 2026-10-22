"""Bounded, evidence-led interpretation and targeted longitudinal research."""

import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from src.core.config import settings
from src.core.constants import DISCUSSION_FULL_EXCERPT_CHARS
from src.core.external_content import wrap_external_content
from src.core.i18n import normalize_language, resolve_language
from src.domains.proactive_discussions.context_store.schemas import (
    ContextItem,
    ContextProposal,
    ProposalRefusal,
)
from src.domains.proactive_discussions.contextualization.classification import classified_evidence
from src.domains.proactive_discussions.contextualization.outcome import ContextTally
from src.domains.proactive_discussions.llm_contracts import ContextInterpretation
from src.domains.proactive_discussions.policy import (
    clamp_research_window,
    effective_sources,
    validate_research_request,
)
from src.domains.proactive_discussions.registry import SOURCE_REGISTRY
from src.domains.proactive_discussions.run_types import ContextOutcome
from src.domains.proactive_discussions.schemas import (
    ContextResolution,
    DiscussionPolicy,
    PriorOpening,
    ReadyContext,
    ResearchContext,
)
from src.domains.shared.discussion_sources import (
    RESEARCH_FUTURE_DAYS_MAX,
    RESEARCH_HISTORY_DAYS_MAX,
    DiscussionEvidence,
    ResearchRequest,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    evidence_identity,
)


@dataclass(frozen=True)
class ContextPublication:
    """What one pass's publication left: the usable items, and what it set aside.

    Attributes:
        items: The stored items usable on the facts the pass analysed.
        refused: Why each proposal the publication could not admit was set aside.
        changed: Whether the publication moved the context's generation.
    """

    items: tuple[ContextItem, ...] = ()
    refused: Counter[ProposalRefusal] = field(default_factory=Counter)
    changed: bool = False


class ContextStore(Protocol):
    """What the context loop needs from the context store, owner-fenced."""

    async def ready_references(self, facts: tuple[DiscussionEvidence, ...]) -> set[str]:
        """Return the references of a stored ready context still valid on these facts."""

    async def remember_ready(self, facts: tuple[DiscussionEvidence, ...]) -> None:
        """Record that these facts make a ready context, for the next run to reuse."""

    async def admit(self, snapshots: tuple[SourceSnapshot, ...]) -> tuple[DiscussionEvidence, ...]:
        """Admit the evidence of a run's pages through the person's controls."""

    async def changed(
        self, facts: tuple[DiscussionEvidence, ...]
    ) -> tuple[DiscussionEvidence, ...]:
        """Return the admitted facts that changed since their last interpretation."""

    async def warm(self, facts: tuple[DiscussionEvidence, ...]) -> tuple[ContextItem, ...]:
        """Return the stored items still usable on these facts."""

    async def publish(
        self,
        proposals: tuple[ContextProposal, ...],
        analysed: tuple[DiscussionEvidence, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> ContextPublication:
        """Publish the proposals and the analysed observations; return what was left."""


class ContextModel(Protocol):
    """The context call: one structured interpretation per complete prompt."""

    async def interpret(self, content: str) -> ContextInterpretation:
        """Run one context call on a complete prompt."""


class SourceReader(Protocol):
    """The bounded, authorised source read the loop researches through."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one source page under the run's authority."""


@dataclass(frozen=True)
class ContextResult:
    """What a context build produced: readiness, evidence, knowledge, pages read, and why.

    ``outcome`` names how the build ended and ``stats`` its counts (never content),
    which the run stores, logs and shows.
    """

    ready: bool
    evidence: tuple[DiscussionEvidence, ...] = ()
    knowledge: tuple[ContextItem, ...] = ()
    snapshots: tuple[SourceSnapshot, ...] = ()
    outcome: ContextOutcome = "context_built"
    stats: dict[str, object] = field(default_factory=dict)


def merge_snapshots(snapshots: tuple[SourceSnapshot, ...]) -> tuple[SourceSnapshot, ...]:
    """Keep, for each evidence, only its newest read, on the page that read it.

    Coverage is never unioned into a fictitious complete history: an earlier
    overlapping read loses the item.

    Args:
        snapshots: The pages read, oldest first.

    Returns:
        The same pages, each holding only the items it read last.
    """
    # Never union coverage into a fictitious complete history. Earlier overlapping
    # observations disappear; only the newest native object version is offered.
    selected: dict[str, tuple[int, DiscussionEvidence]] = {}
    for index, snapshot in enumerate(snapshots):
        for fact in snapshot.items:
            selected[evidence_identity(fact)] = (index, fact)
    return tuple(
        snapshot.model_copy(
            update={"items": tuple(fact for page, fact in selected.values() if page == index)}
        )
        for index, snapshot in enumerate(snapshots)
    )


def context_payload(
    *,
    now: datetime,
    rules: str,
    policy: DiscussionPolicy,
    facts: tuple[DiscussionEvidence, ...],
    knowledge: tuple[ContextItem, ...],
    snapshots: tuple[SourceSnapshot, ...],
    history: tuple[PriorOpening, ...] = (),
    language: str | None = None,
    research_waves: int | None = None,
) -> str:
    """Render the context call's user message: the rules, then the evidence as data.

    Args:
        now: The run's clock.
        rules: The compiled first-party rules, placed before the data.
        policy: The person's policy (timezone, topics, readable sources).
        facts: The evidence offered for interpretation.
        knowledge: The stored items still usable.
        snapshots: The pages read, without their items, as coverage.
        history: Prior openings whose support is current.
        language: The person's language, else the declared one.
        research_waves: The research waves left, stated with the window bounds the
            loop enforces; None leaves the research block out.

    Returns:
        The message, its data wrapped as external content.
    """
    data: dict[str, object] = {
        "language": normalize_language(language) if language is not None else resolve_language(),
        "now": now.isoformat(),
        "timezone": policy.timezone,
        "allowed_topics": policy.sensitive_topics,
        "forbidden_topics": policy.forbidden_topics,
        "available_research": {
            key.value: tuple(SOURCE_REGISTRY[key].operations)
            for key in effective_sources(policy, frozenset(SourceKey))
        },
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "knowledge": [item.model_dump(mode="json") for item in knowledge],
        "coverage": [snapshot.model_dump(mode="json", exclude={"items"}) for snapshot in snapshots],
        "prior_openings": [item.model_dump(mode="json") for item in history],
    }
    if research_waves is not None:
        # The bounds the loop enforces, stated where the model reads them (ADR-184).
        data["research"] = {
            "waves_remaining": research_waves,
            "history_days_max": RESEARCH_HISTORY_DAYS_MAX,
            "future_days_max": RESEARCH_FUTURE_DAYS_MAX,
        }
    return (
        rules
        + "\n"
        + wrap_external_content(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            "proactive_discussions/context",
            "personal_evidence",
        )
    )


class ContextLoop:
    """Build a ready context in at most ``max_passes`` context calls.

    Each pass admits what was read, reuses what is still valid, interprets only
    what changed, then settles on references, asks for one bounded research wave
    or gives up. Nothing the person's controls refuse is published, and no call is
    made on a prompt that does not fit.

    A covering build (a rebuild: no decision follows it) does not stop at the first
    ready resolution: it keeps the ready context and reads on while facts it has not
    interpreted yet remain and passes are left.
    """

    def __init__(
        self,
        owner: UUID,
        run: UUID,
        policy: DiscussionPolicy,
        gateway: SourceReader,
        store: ContextStore,
        model: ContextModel,
        *,
        now: datetime,
        directives: str,
        fits: Callable[[str], bool],
        language: str | None = None,
        max_passes: int | None = None,
        cover_all: bool = False,
        seed_snapshots: tuple[SourceSnapshot, ...] = (),
        verify: (
            Callable[[tuple[DiscussionEvidence, ...], tuple[SourceSnapshot, ...]], Awaitable[None]]
            | None
        ) = None,
    ) -> None:
        self.owner, self.run, self.policy, self.gateway, self.store, self.model = (
            owner,
            run,
            policy,
            gateway,
            store,
            model,
        )
        self.now, self.directives, self.fits = now, directives, fits
        self.seed_snapshots, self.verify, self.cover_all = seed_snapshots, verify, cover_all
        self.language = normalize_language(language) if language is not None else resolve_language()
        self.max_passes = (
            settings.discussion_context_calls_per_run if max_passes is None else max_passes
        )
        # The counts of the build in progress, readable when it stops before its end.
        self.tally = ContextTally()

    async def _read(self, request: ResearchRequest) -> SourceSnapshot:
        return await self.gateway.read(
            SourceReadRequest(
                owner_id=self.owner,
                run_id=self.run,
                policy_revision=self.policy.revision,
                request=request,
                cursor=request.cursor,
                now=self.now,
                window_start=request.start
                or self.now - timedelta(days=settings.discussion_research_default_window_days),
                window_end=request.end
                or self.now + timedelta(days=settings.discussion_research_default_window_days),
                item_limit=settings.discussion_research_item_limit,
                item_max_chars=(
                    DISCUSSION_FULL_EXCERPT_CHARS
                    if request.source == SourceKey.PORTRAIT
                    else settings.discussion_research_item_max_chars
                ),
                call_limit=settings.discussion_read_call_limit,
                timeout_seconds=settings.discussion_read_timeout_seconds,
            )
        )

    def _payload(
        self,
        facts: tuple[DiscussionEvidence, ...],
        warm: tuple[ContextItem, ...],
        snapshots: tuple[SourceSnapshot, ...],
        *,
        waves: int,
    ) -> str:
        return context_payload(
            now=self.now,
            rules=self.directives,
            policy=self.policy,
            facts=facts,
            knowledge=warm,
            snapshots=snapshots,
            language=self.language,
            research_waves=waves,
        )

    def _pack(
        self,
        changed: tuple[DiscussionEvidence, ...],
        warm: tuple[ContextItem, ...],
        snapshots: tuple[SourceSnapshot, ...],
        *,
        waves: int,
    ) -> tuple[DiscussionEvidence, ...]:
        # Round robin sources keeps one busy mailbox from consuming every slot.
        groups = {key: [item for item in changed if item.source == key] for key in SourceKey}
        offered: tuple[DiscussionEvidence, ...] = ()
        for index in range(100):
            for group in groups.values():
                if (
                    index < len(group)
                    and len(offered) < settings.discussion_context_facts_per_pass
                    and self.fits(
                        self._payload((*offered, group[index]), warm, snapshots, waves=waves)
                    )
                ):
                    offered = (*offered, group[index])
        return offered

    async def _recent(self) -> tuple[SourceSnapshot, ...]:
        snapshots: tuple[SourceSnapshot, ...] = ()
        for source in effective_sources(self.policy, frozenset(SourceKey)):
            if "recent" in SOURCE_REGISTRY[source].operations:
                snapshots = (
                    *snapshots,
                    await self._read(ResearchRequest(source=source, operation="recent")),
                )
        return snapshots

    async def _interpret(
        self,
        offered: tuple[DiscussionEvidence, ...],
        warm: tuple[ContextItem, ...],
        snapshots: tuple[SourceSnapshot, ...],
        *,
        waves: int,
    ) -> tuple[ContextInterpretation, tuple[DiscussionEvidence, ...], ContextPublication]:
        checked = {item.reference: item for item in offered}
        checked.update(
            (item.reference, item)
            for page in snapshots
            for item in page.items
            if item.reference in _warm_refs(warm)
        )
        if self.verify is not None:
            await self.verify(tuple(checked.values()), snapshots)
        output = await self.model.interpret(self._payload(offered, warm, snapshots, waves=waves))
        if self.verify is not None:
            await self.verify(tuple(checked.values()), snapshots)
        classified = classified_evidence(output, offered)
        self.tally.facts_unclassified += len(offered) - len(classified)
        allowed = tuple(
            item
            for item in classified
            if set(item.sensitive_topics) <= set(self.policy.sensitive_topics)
        )
        refs = {item.reference for item in allowed} | _warm_refs(warm)
        proposals = tuple(
            proposal
            for proposal in output.proposals
            if set(proposal.references) <= refs
            and set(proposal.sensitive_topics) <= set(self.policy.sensitive_topics)
        )
        published = await self.store.publish(proposals, classified, snapshots)
        updated = {item.id: item for item in (*warm, *published.items)}
        return output, allowed, replace(published, items=tuple(updated.values()))

    async def build(self) -> ContextResult:
        """Run the loop until the context is ready, insufficient or out of passes.

        Returns:
            The context result and its outcome: ready, built (interpreted without a
            ready resolution), unchanged since the last interpretation, or nothing
            interpreted because no fact was admitted (``no_fact``) or none could be
            offered within the configured slot (``prompt_full``).
        """
        tally = self.tally = ContextTally()
        if not self.fits(self._payload((), (), (), waves=self.max_passes - 1)):
            return _ended(ContextResult(False), "prompt_full", tally, ())
        snapshots = (*self.seed_snapshots, *await self._recent())
        attempted: set[str] = set()
        retained: set[str] = set()
        # The ready context a covering build keeps while it reads on.
        settled: ContextResult | None = None
        for turn in range(self.max_passes):
            waves = self.max_passes - 1 - turn
            snapshots = merge_snapshots(snapshots)
            facts = await self.store.admit(snapshots)
            tally.observe(snapshots, facts)
            warm = await self.store.warm(facts)
            tally.items = len(warm)
            changed = _retained_facts(
                await self.store.changed(facts), facts, self._reoffered(retained)
            )
            if not changed:
                if settled is not None:
                    return await self._close(settled, tally, snapshots)
                result = _ready_result(
                    await self.store.ready_references(facts), facts, warm, snapshots
                )
                return _ended(result, _settled_outcome(result, facts), tally, snapshots)
            offered = self._pack(changed, warm, snapshots, waves=waves)
            if not offered:
                return await self._close(settled, tally, snapshots, otherwise="prompt_full")
            retained = {fact.reference for fact in offered}
            tally.facts_offered += len(offered)
            tally.context_calls += 1
            output, allowed, publication = await self._interpret(
                offered, warm, snapshots, waves=waves
            )
            warm = publication.items
            tally.count_proposals(
                len(output.proposals), output.refused_proposals, publication.refused
            )
            if publication.changed:
                tally.context_updates += 1
            tally.items = len(warm)
            if isinstance(output.resolution, ReadyContext):
                result = await self._finish_ready(
                    output.resolution, allowed, facts, retained, warm, snapshots
                )
                if not self.cover_all:
                    return _ended(result, _ready_outcome(result), tally, snapshots)
                settled = _prefer_ready(result, settled)
                continue
            additions = await self._next_wave(output.resolution, waves, snapshots, attempted)
            if additions:
                snapshots = (*snapshots, *additions)
            elif not self.cover_all:
                return _ended(ContextResult(False), "context_built", tally, snapshots)
        return await self._close(settled, tally, snapshots)

    def _reoffered(self, retained: set[str]) -> set[str]:
        """The facts of the last pass to offer again with what changed.

        A covering build offers what it has not interpreted first: the facts of a
        previous pass are checkpointed, and re-offering them would take the places
        of facts nobody has read yet.
        """
        return set() if self.cover_all else retained

    async def _close(
        self,
        settled: ContextResult | None,
        tally: ContextTally,
        snapshots: tuple[SourceSnapshot, ...],
        *,
        otherwise: ContextOutcome = "context_built",
    ) -> ContextResult:
        """End the build on the ready context a covering build kept, else on ``otherwise``.

        Each pass's publication clears the stored ready context, so the one an earlier
        pass settled on is stored again, or the next opening would lose it.
        """
        if settled is None:
            return _ended(ContextResult(False), otherwise, tally, snapshots)
        await self.store.remember_ready(settled.evidence)
        return _ended(settled, "context_ready", tally, snapshots)

    async def _next_wave(
        self,
        resolution: ContextResolution,
        waves: int,
        snapshots: tuple[SourceSnapshot, ...],
        attempted: set[str],
    ) -> tuple[SourceSnapshot, ...]:
        """The pages of the research wave the call asked for, or none worth another pass.

        Nothing comes back when the call asked no research, no wave is left, or the
        research read nothing new.
        """
        if not isinstance(resolution, ResearchContext) or waves == 0:
            return ()
        additions = await self._research(resolution, snapshots, attempted)
        if not additions or _same_versions(snapshots, additions):
            return ()
        return additions

    async def _finish_ready(
        self,
        resolution: ReadyContext,
        allowed: tuple[DiscussionEvidence, ...],
        facts: tuple[DiscussionEvidence, ...],
        retained: set[str],
        warm: tuple[ContextItem, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> ContextResult:
        permitted = {fact.reference: fact for fact in allowed}
        permitted.update(
            (fact.reference, fact)
            for fact in facts
            if fact.reference in _warm_refs(warm) and fact.reference not in retained
        )
        result = _ready_result(
            set(resolution.references), tuple(permitted.values()), warm, snapshots
        )
        if result.ready:
            await self.store.remember_ready(result.evidence)
        return result

    async def _research(
        self,
        resolution: ResearchContext,
        snapshots: tuple[SourceSnapshot, ...],
        attempted: set[str],
    ) -> tuple[SourceSnapshot, ...]:
        additions: tuple[SourceSnapshot, ...] = ()
        for asked in resolution.requests:
            request = clamp_research_window(asked, now=self.now)
            if request is None:
                continue
            try:
                validate_research_request(
                    request, self.policy, snapshots, owner_id=self.owner, now=self.now
                )
            except ValueError:
                # A research the policy or the pages refuse is never read, and never
                # refuses the run either: the others are read.
                self.tally.research_refused += 1
                continue
            key = request.model_dump_json()
            if key not in attempted:
                attempted.add(key)
                additions = (*additions, await self._read(request))
        return additions


def _same_versions(
    previous: tuple[SourceSnapshot, ...], additions: tuple[SourceSnapshot, ...]
) -> bool:
    old = {
        (evidence_identity(fact), fact.version) for snapshot in previous for fact in snapshot.items
    }
    return all(
        (evidence_identity(fact), fact.version) in old
        for snapshot in additions
        for fact in snapshot.items
    )


def _ended(
    result: ContextResult,
    outcome: ContextOutcome,
    tally: ContextTally,
    snapshots: tuple[SourceSnapshot, ...],
) -> ContextResult:
    """A build's result with its outcome, its counts and every page it read."""
    return replace(
        result, outcome=outcome, stats=tally.as_dict(), snapshots=result.snapshots or snapshots
    )


def _ready_outcome(result: ContextResult) -> ContextOutcome:
    """How an opening's build ended on a ready resolution: ready, or built without one."""
    return "context_ready" if result.ready else "context_built"


def _prefer_ready(result: ContextResult, settled: ContextResult | None) -> ContextResult | None:
    """The newest ready context of a covering build, else the one it kept before."""
    return result if result.ready else settled


def _settled_outcome(
    result: ContextResult, facts: tuple[DiscussionEvidence, ...]
) -> ContextOutcome:
    """Why a build with nothing new to interpret ended: reused, empty, or unchanged."""
    if result.ready:
        return "context_ready"
    return "unchanged" if facts else "no_fact"


def _warm_refs(items: tuple[ContextItem, ...]) -> set[str]:
    return {proof.reference for item in items for proof in item.proofs}


def _retained_facts(
    changed: tuple[DiscussionEvidence, ...],
    facts: tuple[DiscussionEvidence, ...],
    retained: set[str],
) -> tuple[DiscussionEvidence, ...]:
    known = {item.reference for item in changed}
    return (
        *changed,
        *(fact for fact in facts if fact.reference in retained and fact.reference not in known),
    )


def _ready_result(
    chosen: set[str],
    facts: tuple[DiscussionEvidence, ...],
    warm: tuple[ContextItem, ...],
    snapshots: tuple[SourceSnapshot, ...],
) -> ContextResult:
    if not chosen or not chosen <= {fact.reference for fact in facts}:
        return ContextResult(False)
    return ContextResult(
        True,
        tuple(fact for fact in facts if fact.reference in chosen),
        tuple(item for item in warm if _warm_refs((item,)) <= chosen),
        snapshots,
    )
