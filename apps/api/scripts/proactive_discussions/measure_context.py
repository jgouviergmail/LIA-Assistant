"""Measure what one proactive-discussion context pass reads, admits and interprets.

Runs inside an API container, for one account named by its e-mail::

    task discussions:context:measure -- --email person@example.org [--mode context --max-usd 0.5]
    docker exec lia-api-dev python -m scripts.proactive_discussions.measure_context --email ...

``--mode read`` (the default) calls no model and commits nothing to the discussion
tables: every session it opens itself is rolled back. It runs the read phase of a run
through the run's own readers, gateway, admission and prompt measure, and prints a
report of COUNTS only — no source content, no personal text.

``--mode verify`` then reads every admitted fact again exactly as a run's
revalidation does before and after each paid call, and counts, source by source,
what came back at the same version, at another, or not at all — with the names of
the fields that differ. It calls no model.

``--mode context`` then runs the run's own context loop on the configured
``discussion_context`` slot, as a rebuild would (every admitted fact offered again),
under an in-memory reservation of ``--max-usd``. It still writes nothing to the
discussion tables: the store keeps the proposals in memory and the reservation is
never persisted. The model's spend is billed to the account like any run's, under
the measurement's own run id (every euro the platform pays is attributed). The
cached read restriction is applied as found; a stale one is reported, not compiled.

The paid weather read is refused, so the weather page appears closed, unless
``--paid-weather`` asks for it: it is then read as a run reads it, billed to the
account under the measurement's run id like every other spend of the measurement.
Connector reads behave as in a run (a token may be refreshed). Every source the
measurement opens is filed in the consultation register under its run id, as a read
the person asked for. Every report line starts with ``§`` so it can be told apart
from the application logs.
"""

import argparse
import asyncio
import statistics
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import select

import src.infrastructure.observability.logging_bootstrap  # noqa: F401  (configure logging first)
from src.core.config import settings
from src.core.constants import (
    DISCUSSION_FULL_EXCERPT_CHARS,
    DISCUSSION_PROMPT_FRAMING_TOKENS,
    DISCUSSION_REREAD_ITEM_LIMIT,
)
from src.core.i18n import normalize_language
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    get_llm_config_for_agent,
)
from src.core.llm_usage import LLMBillingRecord
from src.core.read_budget import ReadCallBudget
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.proactive_discussions.consultations import reads_requested_by_person
from src.domains.proactive_discussions.context_store.admission import (
    observation_key,
    reference_key,
    support_key,
)
from src.domains.proactive_discussions.context_store.candidates import pending_proofs
from src.domains.proactive_discussions.context_store.checkpoints import interpretation_signature
from src.domains.proactive_discussions.context_store.observations import changed_observations
from src.domains.proactive_discussions.context_store.preparation import prepare_items
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.restrictions import restrict_cached_topics
from src.domains.proactive_discussions.context_store.schemas import ContextItem, ContextProposal
from src.domains.proactive_discussions.contextualization.loop import (
    ContextLoop,
    ContextPublication,
    context_payload,
    merge_snapshots,
)
from src.domains.proactive_discussions.finance_permit import (
    DiscretionaryBudgetRefused,
    NativeSpendPermit,
    context_call_budget,
)
from src.domains.proactive_discussions.finance_repository import SpendReservation
from src.domains.proactive_discussions.llm_contracts import (
    ContextInterpretation,
    DiscussionPhase,
    bounded_prompt_tokens,
)
from src.domains.proactive_discussions.models import DiscussionPreference
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.rule_controls import RuleCache
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    evidence_identity,
)
from src.domains.users.models import User
from src.infrastructure.cache.pricing_cache import (
    get_cached_usd_eur_rate,
    load_published_pricing_cache,
)
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import AsyncSessionLocal, get_db_context
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.proactive.discussion_control import ControlSnapshot, preview_controls
from src.infrastructure.proactive.discussion_llm import DiscussionLLM, DiscussionSource
from src.infrastructure.proactive.discussion_revalidation import _request as revalidation_request
from src.infrastructure.proactive.discussion_run_setup import first_call_bound
from src.infrastructure.proactive.discussion_runner import (
    fits_context,
    policy_loader,
    rule_cache_signature,
)
from src.infrastructure.proactive.discussion_sources import discussion_readers
from src.infrastructure.proactive.tracking import out_of_turn_spend


def emit(text: str) -> None:
    """Print one report line, marked so it can be filtered out of the logs."""
    print(f"§ {text}", flush=True)


@dataclass
class Shape:
    """What the account brings to a pass: policy, controls, language, stored context."""

    owner: UUID
    policy: DiscussionPolicy
    context_epoch: int
    controls: ControlSnapshot
    language: str
    denied: tuple[SourceKey, ...]
    abstain: bool
    rule_cache_current: bool
    stored_items: int


@dataclass
class SourceRow:
    """One source page as the report shows it."""

    source: str
    status: str
    reason: str | None
    items: int
    excerpt_max: int
    admitted: int = 0
    refused: Counter[str] = field(default_factory=Counter)


class _NoStore:
    """The read phase never writes context: any store call is a defect of this script."""

    async def ready_references(self, facts: tuple[DiscussionEvidence, ...]) -> set[str]:
        raise RuntimeError("the read phase does not consult the store")

    async def remember_ready(self, facts: tuple[DiscussionEvidence, ...]) -> None:
        raise RuntimeError("the read phase does not consult the store")

    async def admit(self, snapshots: tuple[SourceSnapshot, ...]) -> tuple[DiscussionEvidence, ...]:
        raise RuntimeError("the read phase does not consult the store")

    async def changed(
        self, facts: tuple[DiscussionEvidence, ...]
    ) -> tuple[DiscussionEvidence, ...]:
        raise RuntimeError("the read phase does not consult the store")

    async def warm(self, facts: tuple[DiscussionEvidence, ...]) -> tuple[ContextItem, ...]:
        raise RuntimeError("the read phase does not consult the store")

    async def publish(
        self,
        proposals: tuple[ContextProposal, ...],
        analysed: tuple[DiscussionEvidence, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> ContextPublication:
        raise RuntimeError("the read phase does not consult the store")


class _NoModel:
    """The read phase calls no model: any call is a defect of this script."""

    async def interpret(self, content: str) -> ContextInterpretation:
        raise RuntimeError("the read phase calls no model")


class _DryStore:
    """A rebuild's store that reads the real controls and keeps every write in memory.

    Admission goes through the real repository in rolled-back sessions. Every fact is
    to interpret on the first pass, as after a rebuild's new epoch; what a pass
    analysed is checkpointed in memory, so the next pass offers the rest. Each
    proposal is prepared as the real publication prepares it (``prepare_items``), so
    what its evidence cannot carry is counted by reason; nothing is stored.
    """

    def __init__(self, shape: Shape, policy: DiscussionPolicy) -> None:
        self.shape, self.policy = shape, policy
        self.sources = effective_sources(policy, frozenset(SourceKey))
        self.kinds: Counter[str] = Counter()
        self.qualifications: Counter[str] = Counter()
        self.sensitive_items = 0
        self.refused: Counter[str] = Counter()
        self.analysed = 0
        self.ready_facts = 0
        self.checkpoints: set[tuple[str, str]] = set()

    async def ready_references(self, facts: tuple[DiscussionEvidence, ...]) -> set[str]:
        return set()

    async def remember_ready(self, facts: tuple[DiscussionEvidence, ...]) -> None:
        self.ready_facts = len(facts)

    async def admit(self, snapshots: tuple[SourceSnapshot, ...]) -> tuple[DiscussionEvidence, ...]:
        async with AsyncSessionLocal() as db:
            try:
                return await ContextRepository(db).filter_inputs(
                    self.shape.owner,
                    snapshots,
                    allowed_sources=self.sources,
                    allowed_topics=frozenset(self.policy.sensitive_topics),
                    now=datetime.now(UTC),
                    directives_revision=self.shape.controls.revision,
                )
            finally:
                await db.rollback()

    async def changed(
        self, facts: tuple[DiscussionEvidence, ...]
    ) -> tuple[DiscussionEvidence, ...]:
        return tuple(
            fact for fact in facts if (fact.reference, fact.version) not in self.checkpoints
        )

    async def warm(self, facts: tuple[DiscussionEvidence, ...]) -> tuple[ContextItem, ...]:
        return ()

    async def publish(
        self,
        proposals: tuple[ContextProposal, ...],
        analysed: tuple[DiscussionEvidence, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> ContextPublication:
        self.analysed += len(analysed)
        self.checkpoints |= {(fact.reference, fact.version) for fact in analysed}
        classified = {item.reference: item for item in analysed}
        offered = tuple(
            page.model_copy(
                update={"items": tuple(classified.get(item.reference, item) for item in page.items)}
            )
            for page in snapshots
        )
        items, refused = prepare_items(
            self.shape.owner,
            proposals,
            {item.reference: item for item in await self.admit(offered)},
            allowed_topics=frozenset(self.policy.sensitive_topics),
            generation=1,
            now=datetime.now(UTC),
            coverage=offered,
            timezone=self.policy.timezone,
        )
        self.refused.update(refused)
        for item in items:
            self.kinds[item.kind] += 1
            self.qualifications[item.qualification] += 1
            self.sensitive_items += any(proof.sensitive_topics for proof in item.proofs)
        return ContextPublication((), refused)


class _MeteredPermit(NativeSpendPermit):
    """The run's own permit, also counting what each admitted call reported."""

    def __init__(self, reservation: SpendReservation) -> None:
        async def unpersisted(amount: Decimal, committed: Decimal) -> None:
            return None

        # A rebuild's own budget: it interprets every admitted fact it can afford.
        super().__init__(
            reservation, issue=unpersisted, context_calls=context_call_budget(context_only=True)
        )
        self.calls: list[dict[str, int]] = []

    async def admit(self, phase: DiscussionPhase, config: LLMAgentConfig, tokens: int) -> None:
        await super().admit(phase, config, tokens)
        self.calls.append({"prompt_measured": tokens})

    def record(self, records: tuple[LLMBillingRecord, ...], *, uncertain: bool) -> None:
        super().record(records, uncertain=uncertain)
        if self.calls and records:
            self.calls[-1].update(
                tokens_in=sum(r.tokens_in for r in records),
                tokens_out=sum(r.tokens_out for r in records),
                tokens_cache=sum(r.tokens_cache for r in records),
            )


class _MeasuredModel(DiscussionLLM):
    """The run's own model adapter, also counting each interpretation's shape."""

    def __init__(
        self,
        owner_id: UUID,
        run_id: UUID,
        permit: _MeteredPermit,
        *,
        authorize: Callable[[], Awaitable[None]],
        source: DiscussionSource,
    ) -> None:
        super().__init__(owner_id, run_id, permit, authorize=authorize, source=source)
        self.resolutions: Counter[str] = Counter()
        self.classified = 0
        self.classified_sensitive = 0
        self.readable = 0
        self.refused: Counter[str] = Counter()

    async def interpret(self, content: str) -> ContextInterpretation:
        output = await super().interpret(content)
        self.resolutions[output.resolution.status] += 1
        self.classified += len(output.classifications)
        self.classified_sensitive += sum(
            bool(item.sensitive_topics) for item in output.classifications
        )
        self.readable += len(output.proposals)
        self.refused.update(output.refused_proposals)
        return output


async def _refuse_paid_weather() -> None:
    raise DiscretionaryBudgetRefused(
        "tariff_unavailable", "measurement: the paid weather read is excluded"
    )


async def _bill_paid_weather() -> None:
    # No reservation to take: the measurement's accounting records every Google call.
    return None


async def _shape(email: str, now: datetime) -> Shape:
    async with get_db_context() as db:
        owner = await db.scalar(select(User.id).where(User.email == email))
        if owner is None:
            raise SystemExit("no account with that e-mail")
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    # The tariffs the workers published: read, never republished (a measurement
    # must not touch the caches every worker shares).
    if not await load_published_pricing_cache():
        emit("note: no tariff could be loaded; every paid call will be refused")
    async with AsyncSessionLocal() as db:
        try:
            policy = await DiscussionRepository(db).get_policy(owner)
            epoch = await db.scalar(
                select(DiscussionPreference.context_epoch).where(
                    DiscussionPreference.user_id == owner
                )
            )
            controls = await preview_controls(db, owner, now=now)
            language = normalize_language(
                await db.scalar(select(User.language).where(User.id == owner))
            )
            state = await ContextRepository(db)._state(owner)
            cache = RuleCache.model_validate(state.rule_cache) if state.rule_cache else None
            stored = await pending_proofs(
                db,
                owner,
                sources=frozenset(policy.sources),
                topics=frozenset(policy.sensitive_topics),
                now=now,
            )
        finally:
            await db.rollback()
    current = bool(
        cache
        and cache.signature == rule_cache_signature(controls, policy)
        and cache.expires_at > now
    )
    return Shape(
        owner=owner,
        policy=policy,
        context_epoch=int(epoch or 0),
        controls=controls,
        language=language,
        denied=tuple(cache.denied) if cache else (),
        abstain=bool(cache and cache.abstain),
        rule_cache_current=current,
        stored_items=len(stored),
    )


def _narrowed(shape: Shape) -> DiscussionPolicy:
    allowed = (
        () if shape.abstain else tuple(k for k in shape.policy.sources if k not in shape.denied)
    )
    return shape.policy.model_copy(update={"sources": allowed})


def _gateway(shape: Shape, policy: DiscussionPolicy, *, paid_weather: bool) -> SourceGateway:
    """The run's own gateway, under one run's read-call budget, as a run builds it."""

    async def narrowed_loader(owner: UUID) -> DiscussionPolicy:
        current = await policy_loader(owner)
        return current.model_copy(
            update={"sources": tuple(key for key in current.sources if key in policy.sources)}
        )

    return SourceGateway(
        discussion_readers(
            authorize_weather=_bill_paid_weather if paid_weather else _refuse_paid_weather
        ),
        narrowed_loader,
        call_budget=ReadCallBudget(owner=shape.owner, limit=settings.discussion_run_read_calls_max),
    )


async def _read(
    shape: Shape, policy: DiscussionPolicy, now: datetime, gateway: SourceGateway
) -> tuple[SourceSnapshot, ...]:
    loop = ContextLoop(
        shape.owner,
        uuid4(),
        policy,
        gateway,
        _NoStore(),
        _NoModel(),
        now=now,
        directives=shape.controls.text,
        fits=fits_context,
        language=shape.language,
    )
    return merge_snapshots(await loop._recent())


def _refusal(
    item: DiscussionEvidence,
    *,
    sources: frozenset[SourceKey],
    topics: frozenset[str],
    excluded: frozenset[str],
    forgotten: dict[str, str],
    forgotten_at: datetime | None,
    now: datetime,
) -> str | None:
    supports = {support_key(value) for value in item.supports}
    roots = {observation_key(item), *supports}
    if item.source not in sources:
        return "source"
    if not set(item.required_sources) <= sources:
        return "required_source"
    if not set(item.sensitive_topics) <= topics:
        return "sensitive_topic"
    if roots & excluded:
        return "excluded"
    if supports & forgotten.keys():
        return "forgotten_support"
    if item.expires_at is not None and item.expires_at <= now:
        return "expired"
    previous = forgotten.get(observation_key(item))
    if previous is not None and previous == item.version:
        return "forgotten"
    if previous is None and forgotten_at is not None:
        dated = item.recorded_at or item.occurred_at
        if dated is None or dated <= forgotten_at:
            return "forgotten_by_purge"
    return None


async def _admit(
    shape: Shape, policy: DiscussionPolicy, pages: tuple[SourceSnapshot, ...], now: datetime
) -> tuple[list[SourceRow], tuple[DiscussionEvidence, ...], int]:
    items = tuple(item for page in pages for item in page.items)
    roots = tuple(
        {
            root
            for item in items
            for root in (
                observation_key(item),
                reference_key(item.reference),
                *(support_key(value) for value in item.supports),
            )
        }
    )
    sources = effective_sources(policy, frozenset(SourceKey))
    topics = frozenset(policy.sensitive_topics)
    async with AsyncSessionLocal() as db:
        try:
            controls = await ContextRepository(db).controls(shape.owner, roots=roots)
            restricted = await restrict_cached_topics(
                db, shape.owner, items, now=now, directives_revision=shape.controls.revision
            )
            to_interpret = await changed_observations(
                db,
                shape.owner,
                restricted,
                now=now,
                signature=interpretation_signature(policy, shape.language),
                directives_revision=shape.controls.revision,
                context_epoch=shape.context_epoch,
            )
        finally:
            await db.rollback()
    by_reference = {item.reference: item for item in restricted}
    rows: list[SourceRow] = []
    admitted: list[DiscussionEvidence] = []
    for page in pages:
        row = SourceRow(
            source=page.source.value,
            status=page.status,
            reason=page.reason,
            items=len(page.items),
            excerpt_max=max((len(item.excerpt) for item in page.items), default=0),
        )
        for raw in page.items:
            item = by_reference[raw.reference]
            cause = _refusal(
                item,
                sources=sources,
                topics=topics,
                excluded=controls.excluded_roots,
                forgotten=controls.forgotten_versions,
                forgotten_at=controls.forgotten_at,
                now=now,
            )
            if cause is None:
                row.admitted += 1
                admitted.append(item)
            else:
                row.refused[cause] += 1
        rows.append(row)
    return rows, tuple(admitted), len(to_interpret)


def _measure(content: str) -> int:
    """The prompt size the run's own measure gives, without its ceiling."""
    return bounded_prompt_tokens(
        load_prompt("discussion_context_prompt", settings.discussion_context_prompt_version),
        content,
        schema=ContextInterpretation,
        window=sys.maxsize,
        output=1,
    )


def _payload(
    shape: Shape,
    policy: DiscussionPolicy,
    pages: tuple[SourceSnapshot, ...],
    facts: tuple[DiscussionEvidence, ...] = (),
) -> str:
    return context_payload(
        now=datetime.now(UTC),
        rules=shape.controls.text,
        policy=policy,
        facts=facts,
        knowledge=(),
        snapshots=pages,
        language=shape.language,
        research_waves=max(0, settings.discussion_context_calls_per_run - 1),
    )


def _envelope(
    shape: Shape, policy: DiscussionPolicy, pages: tuple[SourceSnapshot, ...]
) -> dict[str, int]:
    config = get_llm_config_for_agent(settings, "discussion_context")
    window = get_effective_context_window_for_slot("discussion_context")
    return {
        "slot_window": window,
        "slot_max_tokens": config.max_tokens,
        "ceiling": window - config.max_tokens - DISCUSSION_PROMPT_FRAMING_TOKENS,
        "rules": _measure(shape.controls.text) - _measure(""),
        "before_reading": _measure(_payload(shape, policy, ())),
        "after_reading": _measure(_payload(shape, policy, pages)),
    }


def _fact_costs(
    shape: Shape,
    policy: DiscussionPolicy,
    pages: tuple[SourceSnapshot, ...],
    facts: tuple[DiscussionEvidence, ...],
) -> list[int]:
    base = _measure(_payload(shape, policy, pages))
    return sorted(_measure(_payload(shape, policy, pages, (fact,))) - base for fact in facts)


async def _report_read(
    shape: Shape, policy: DiscussionPolicy, now: datetime, gateway: SourceGateway
) -> tuple[tuple[SourceSnapshot, ...], tuple[DiscussionEvidence, ...]]:
    emit(
        f"owner {str(shape.owner)[:8]}  enabled={shape.policy.enabled}  "
        f"revision={shape.policy.revision}  epoch={shape.context_epoch}"
    )
    emit(
        f"consented sensitive topics={len(shape.policy.sensitive_topics)}  "
        f"forbidden topics={len(shape.policy.forbidden_topics)}  "
        f"consented sources={len(shape.policy.sources)}"
    )
    emit(
        f"rule supports={len(shape.controls.supports)}  "
        f"cached read restriction: denied={len(shape.denied)} abstain={shape.abstain} "
        f"current={shape.rule_cache_current}  stored items with proofs={shape.stored_items}"
    )
    emit(f"effective sources={len(effective_sources(policy, frozenset(SourceKey)))}")
    started = perf_counter()
    pages = await _read(shape, policy, now, gateway)
    emit(f"read phase: {len(pages)} pages in {perf_counter() - started:.1f}s")
    rows, admitted, to_interpret_opening = await _admit(shape, policy, pages, now)
    emit("source               status       reason       items  admitted  excerpt_max  refused")
    for row in sorted(rows, key=lambda value: value.source):
        refused = (
            ",".join(f"{cause}:{count}" for cause, count in sorted(row.refused.items())) or "-"
        )
        emit(
            f"{row.source:<20} {row.status:<12} {str(row.reason or '-'):<12} {row.items:>5}  "
            f"{row.admitted:>8}  {row.excerpt_max:>11}  {refused}"
        )
    totals = Counter(row.status for row in rows)
    emit(f"pages by status: {dict(sorted(totals.items()))}")
    emit(
        f"facts read={sum(row.items for row in rows)}  admitted={len(admitted)}  "
        f"to interpret (rebuild)={len(admitted)}  (opening run)={to_interpret_opening}"
    )
    envelope = _envelope(shape, policy, pages)
    emit("envelope " + " ".join(f"{key}={value}" for key, value in envelope.items()))
    bound = first_call_bound(shape.controls.text, policy, shape.language, now=now)
    run = settings.discussion_run_budget_usd
    emit(f"first call bound usd={bound:.6f}  run ceiling usd={run}")
    room = envelope["ceiling"] - envelope["after_reading"]
    costs = _fact_costs(shape, policy, pages, admitted)
    if costs:
        emit(
            f"fact token cost: min={costs[0]} median={int(statistics.median(costs))} "
            f"max={costs[-1]}  room={room}  facts fitting alone={sum(c <= room for c in costs)}  "
            f"facts per pass={settings.discussion_context_facts_per_pass}"
        )
    else:
        emit(f"no admitted fact; room={room}")
    return pages, admitted


_COMPARED = (
    "reference",
    "object_id",
    "recorded_at",
    "occurred_at",
    "planned_date",
    "assertion",
    "category",
    "excerpt_truncated",
    "occurrence_state",
)


def _differences(old: DiscussionEvidence, new: DiscussionEvidence) -> list[str]:
    names = [name for name in _COMPARED if getattr(old, name) != getattr(new, name)]
    if old.excerpt != new.excerpt:
        names.append(f"excerpt({len(old.excerpt)}->{len(new.excerpt)} chars)")
    return names or ["version only"]


async def _measure_verify(
    shape: Shape,
    pages: tuple[SourceSnapshot, ...],
    admitted: tuple[DiscussionEvidence, ...],
    run_id: UUID,
    gateway: SourceGateway,
) -> None:
    """Read every admitted fact again as ``revalidate_evidence`` does, and count.

    The read phase's gateway is reused, so its read-call budget is the run's.
    """
    verdicts: dict[str, Counter[str]] = {}
    for fact in admitted:
        page = next(p for p in pages if any(i.reference == fact.reference for i in p.items))
        fresh = await gateway.read(
            SourceReadRequest(
                owner_id=shape.owner,
                run_id=run_id,
                policy_revision=shape.policy.revision,
                request=revalidation_request(fact, page),
                now=datetime.now(UTC),
                window_start=page.window_start,
                window_end=page.window_end,
                item_limit=DISCUSSION_REREAD_ITEM_LIMIT,
                item_max_chars=DISCUSSION_FULL_EXCERPT_CHARS,
                call_limit=settings.discussion_read_call_limit,
                timeout_seconds=settings.discussion_read_timeout_seconds,
            )
        )
        current = next(
            (item for item in fresh.items if evidence_identity(item) == evidence_identity(fact)),
            None,
        )
        if current is None:
            verdict = f"missing(page {fresh.status}{':' + fresh.reason if fresh.reason else ''})"
        elif current.version == fact.version:
            verdict = "same"
        else:
            verdict = "changed:" + "+".join(_differences(fact, current))
        verdicts.setdefault(fact.source.value, Counter())[verdict] += 1
    for source, counter in sorted(verdicts.items()):
        emit(f"verify {source:<20} " + "  ".join(f"{k}={v}" for k, v in sorted(counter.items())))


async def measure(email: str, *, mode: str, max_usd: Decimal, paid_weather: bool) -> None:
    """Run the requested measurement for one account and print the report."""
    now = datetime.now(UTC)
    shape = await _shape(email, now)
    policy = _narrowed(shape)
    run_id = uuid4()
    emit(f"measurement run {str(run_id)[:8]}")
    gateway = _gateway(shape, policy, paid_weather=paid_weather)
    # The person asked for this measurement: its reads are filed as theirs (ADR-263),
    # and whatever it bills is filed under its run id, like a run's whole act.
    with reads_requested_by_person(True):
        async with (
            consultation_collector(str(run_id)),
            out_of_turn_spend(str(run_id), shape.owner, "proactive_discussions"),
        ):
            pages, admitted = await _report_read(shape, policy, now, gateway)
            if mode == "verify":
                await _measure_verify(shape, pages, admitted, run_id, gateway)
            if mode == "context":
                await _measure_context(
                    shape, policy, run_id, now=now, max_usd=max_usd, paid_weather=paid_weather
                )


async def _measure_context(
    shape: Shape,
    policy: DiscussionPolicy,
    run_id: UUID,
    *,
    now: datetime,
    max_usd: Decimal,
    paid_weather: bool,
) -> None:
    if not shape.rule_cache_current and shape.controls.supports:
        emit("note: the read restriction is stale; a real run would spend one call compiling it")
    permit = _MeteredPermit(
        SpendReservation(owner_id=shape.owner, run_id=run_id, day=now.date(), amount=max_usd)
    )
    store = _DryStore(shape, policy)

    async def authorized() -> None:
        return None

    model = _MeasuredModel(shape.owner, run_id, permit, authorize=authorized, source="user")
    loop = ContextLoop(
        shape.owner,
        run_id,
        policy,
        _gateway(shape, policy, paid_weather=paid_weather),
        store,
        model,
        now=now,
        directives=shape.controls.text,
        fits=fits_context,
        language=shape.language,
        max_passes=permit.context_calls,
        cover_all=True,
    )
    started = perf_counter()
    result = await loop.build()
    elapsed = perf_counter() - started
    emit(f"context outcome={result.outcome} in {elapsed:.1f}s")
    emit("stats " + " ".join(f"{key}={value}" for key, value in result.stats.items()))
    for index, call in enumerate(permit.calls, start=1):
        emit(f"call {index}: " + " ".join(f"{key}={value}" for key, value in call.items()))
    rate = Decimal(str(get_cached_usd_eur_rate()))
    emit(
        f"spend usd={permit.actual_usd:.6f} eur={permit.actual_usd * rate:.6f}  "
        f"reservation usd={max_usd}  uncertain={permit.uncertain}"
    )
    emit(
        f"resolutions={dict(model.resolutions)}  classified={model.classified}  "
        f"classified sensitive={model.classified_sensitive}  analysed={store.analysed}  "
        f"distinct facts interpreted={len(store.checkpoints)}"
    )
    emit(
        f"proposals readable={model.readable}  refused while read={dict(model.refused)}  "
        f"refused at publication={dict(store.refused)}"
    )
    emit(
        f"items kept (all passes) by kind={dict(store.kinds)}  "
        f"qualifications={dict(store.qualifications)}  sensitive items={store.sensitive_items}"
    )
    emit(f"ready={result.ready}  ready facts={store.ready_facts}  evidence={len(result.evidence)}")


def main() -> int:
    """Parse the arguments and run the requested measurement."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True, help="The account to measure.")
    parser.add_argument("--mode", choices=("read", "verify", "context"), default="read")
    parser.add_argument(
        "--max-usd",
        type=Decimal,
        default=Decimal("0.5"),
        help="The in-memory reservation the context mode may spend, in USD.",
    )
    parser.add_argument(
        "--paid-weather",
        action="store_true",
        help="Read the paid weather source as a run does, billed to the account.",
    )
    args = parser.parse_args(sys.argv[1:])
    if args.max_usd <= 0:
        raise SystemExit("--max-usd must be positive")
    import_all_models()
    asyncio.run(
        measure(args.email, mode=args.mode, max_usd=args.max_usd, paid_weather=args.paid_weather)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
