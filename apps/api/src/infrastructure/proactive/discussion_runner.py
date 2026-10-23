"""Native discretionary producer; all network work happens outside SQL transactions."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import settings
from src.core.exceptions import AuthorizationError, UsageLimitExceededError
from src.core.external_content import wrap_external_content
from src.core.read_budget import ReadCallBudget
from src.domains.agents.effects.out_of_turn_effects import proactive_discussion_effect
from src.domains.conversations.service import ConversationService
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.domains.proactive_discussions.backoff import retry_deadline
from src.domains.proactive_discussions.consultations import reads_requested_by_person
from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.proactive_discussions.contextualization.loop import (
    ContextLoop,
    ContextResult,
    context_payload,
)
from src.domains.proactive_discussions.contextualization.outcome import NOTHING_INTERPRETED
from src.domains.proactive_discussions.finance_permit import (
    DiscretionaryBudgetRefused,
    NativeSpendPermit,
    context_call_budget,
)
from src.domains.proactive_discussions.finance_repository import BudgetLimits, SpendRepository
from src.domains.proactive_discussions.history import relevant_opening_history
from src.domains.proactive_discussions.llm_contracts import (
    ContextInterpretation,
    PromptBudgetExceeded,
)
from src.domains.proactive_discussions.policy import effective_sources, validate_decision
from src.domains.proactive_discussions.publication_types import OpeningDraft
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.rule_controls import RuleCache, restricted_sources
from src.domains.proactive_discussions.run_types import RunReason, SettledRunState
from src.domains.proactive_discussions.schemas import (
    DeferDecision,
    DiscussionDecision,
    DiscussionPolicy,
    EngageDecision,
)
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.shared.discussion_directives import DirectiveBudgetExceeded
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceSnapshot,
    semantic_version,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_proactive_discussions import (
    proactive_discussion_runs_total,
)
from src.infrastructure.proactive.discussion_attention import DiscussionAuthority, InitiativeStopped
from src.infrastructure.proactive.discussion_context import NativeContextStore
from src.infrastructure.proactive.discussion_control import ControlSnapshot
from src.infrastructure.proactive.discussion_delivery import dispatch_discussion
from src.infrastructure.proactive.discussion_llm import DiscussionLLM, prepare_call
from src.infrastructure.proactive.discussion_persistence import publication_repository
from src.infrastructure.proactive.discussion_proofs import hydrate_proofs
from src.infrastructure.proactive.discussion_revalidation import revalidate_evidence
from src.infrastructure.proactive.discussion_run_setup import (
    DiscussionRunSetup,
    RunNotStarted,
    configured_limits,
    initialize_run,
    issue_spend,
)
from src.infrastructure.proactive.discussion_sources import discussion_readers
from src.infrastructure.proactive.tracking import out_of_turn_spend
from src.infrastructure.streaming.run_stream_broker import active_run_lease

logger = structlog.get_logger(__name__)


class ExternalReceipt(BaseModel):
    """A billed request's cost, outside model calls, validated finite and non-negative."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    cost_usd: Decimal = Field(ge=0)


def fits_context(payload: str) -> bool:
    """Whether a context call on this payload fits its slot's envelope.

    Args:
        payload: The complete user message.

    Returns:
        False when the prompt would exceed its envelope.
    """
    try:
        prepare_call("context", payload, ContextInterpretation)
    except PromptBudgetExceeded:
        return False
    return True


async def policy_loader(owner: UUID) -> DiscussionPolicy:
    """Read the account's current policy, with the operator's switch read fresh.

    Args:
        owner: The account.

    Returns:
        The policy.

    Raises:
        AuthorizationError: The capability is switched off.
    """
    async with get_db_context() as db:
        await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
        return await DiscussionRepository(db).get_policy(owner)


class DiscussionAct:
    """One funded run's work: context, decision, wording, publication, each re-authorised.

    It holds the run's authority check, its source gateway under the run's read-call budget,
    its context store and its model slots; ``published`` names the opening once
    committed and ``retry_after`` a deferral the decision asked for.
    """

    def __init__(self, setup: DiscussionRunSetup, permit: NativeSpendPermit) -> None:
        self.setup, self.permit = setup, permit
        self.authority = DiscussionAuthority(
            setup.claim, setup.controls.revision, context_only=setup.context_only
        )
        self.policy = setup.policy
        self.context_passes = permit.context_calls
        self.gateway = SourceGateway(
            discussion_readers(authorize_weather=self.weather_allowance),
            self.source_policy,
            call_budget=ReadCallBudget(
                owner=setup.claim.owner_id, limit=settings.discussion_run_read_calls_max
            ),
        )
        self.store = NativeContextStore(
            setup.claim, setup.policy, setup.controls.revision, setup.language
        )
        self.model = DiscussionLLM(
            setup.claim.owner_id,
            setup.claim.run_id,
            permit,
            authorize=self.authority.check,
            # Only a person's request (button, tool, "incorrect" feedback) sets a refresh.
            source="user" if setup.context_only else "proactive",
        )
        self.paid_weather_reads = 0
        self.retry_after: datetime | None = None
        self.published: UUID | None = None
        # Why the run ends as it does, and what its build read and interpreted.
        self.reason: RunReason | None = None
        self.stats: dict[str, object] | None = None
        # The context build in progress: its counts survive a build that stops.
        self.context: ContextLoop | None = None

    async def source_policy(self, owner: UUID) -> DiscussionPolicy:
        """Return the policy a source read runs under, after checking the run's authority.

        The current policy, narrowed to the sources the run started with, so a read
        never outlives a withdrawal.

        Args:
            owner: The account.

        Returns:
            The narrowed policy.
        """
        await self.authority.check()
        current = await policy_loader(owner)
        return current.model_copy(
            update={"sources": tuple(key for key in current.sources if key in self.policy.sources)}
        )

    async def apply_read_controls(self) -> None:
        """Narrow the run's sources by the person's statements, compiled at most daily.

        The compilation is cached under a signature of its inputs (the controls, the
        consented sources and the prompt version, never the policy's revision counter);
        a fresh one spends a context call, so the run keeps one pass less for its
        context. An abstention leaves no source to read.
        """
        controls = self.setup.controls
        if not controls.supports:
            return
        signature = rule_cache_signature(controls, self.policy)
        cached = await self.store.read_rule_cache()
        now = datetime.now(UTC)
        if cached is None or cached.signature != signature or cached.expires_at <= now:
            content = json.dumps(
                {
                    "sources": tuple(self.policy.sources),
                    "supports": [item.model_dump(mode="json") for item in controls.supports],
                },
                ensure_ascii=False,
            )
            compiled = await self.model.compile_rules(content)
            allowed = restricted_sources(compiled, controls.supports, self.policy.sources)
            cached = RuleCache(
                signature=signature,
                expires_at=now + timedelta(hours=settings.discussion_rule_cache_hours),
                denied=tuple(key for key in self.policy.sources if key not in allowed),
                abstain=compiled.abstain,
            )
            await self.store.save_rule_cache(cached)
            # The compilation spent one of the run's context calls.
            self.context_passes = self.permit.context_calls - 1
        allowed = (
            ()
            if cached.abstain
            else tuple(key for key in self.policy.sources if key not in cached.denied)
        )
        self.policy = self.policy.model_copy(update={"sources": allowed})
        self.store.policy = self.policy
        self.store.sources = effective_sources(self.policy, frozenset(SourceKey))

    async def weather_allowance(self) -> None:
        """Reserve the upper cost of one paid weather read before it is made.

        Raises:
            DiscretionaryBudgetRefused: The weather tariff is unknown, or the
                reservation has no room for it.
        """
        endpoints = ("/v1/currentConditions:lookup", "/v1/forecast/hours:lookup")
        if not all(
            GoogleApiPricingService.has_tariff("weather", endpoint) for endpoint in endpoints
        ):
            raise DiscretionaryBudgetRefused("tariff_unavailable", "weather tariff unavailable")
        maximum = (
            max(
                GoogleApiPricingService.get_cost_per_request("weather", endpoint)[0]
                for endpoint in endpoints
            )
            # A paid read may make its whole call budget at the dearest endpoint.
            * settings.discussion_read_call_limit
        )
        await self.permit.reserve_external(maximum)
        self.paid_weather_reads += 1

    async def build(self) -> ContextResult:
        """Build the run's context: rules, then stored proofs read again, then the loop.

        Returns:
            The context result; not ready when the prompt cannot fit, no source is left
            after the person's rules, or the loop found nothing usable.
        """
        await self.authority.check()
        if not fits_context(
            context_payload(
                now=datetime.now(UTC),
                rules=self.setup.controls.text,
                policy=self.policy,
                facts=(),
                knowledge=(),
                snapshots=(),
                language=self.setup.language,
            )
        ):
            return ContextResult(False, outcome="prompt_full")
        await self.apply_read_controls()
        if not self.policy.sources:
            return ContextResult(False, outcome="no_source")
        result = await self._loop()
        # What was read is recorded even when nothing was published: the settings
        # page shows the latest coverage of every source a run opened.
        await self.store.record_coverage(result.snapshots)
        return result

    async def _loop(self) -> ContextResult:
        seeds = await hydrate_proofs(
            self.setup.claim,
            await self.store.proof_candidates(),
            self.gateway,
            now=datetime.now(UTC),
        )
        self.context = ContextLoop(
            self.setup.claim.owner_id,
            self.setup.claim.run_id,
            self.policy,
            self.gateway,
            self.store,
            self.model,
            now=datetime.now(UTC),
            directives=self.setup.controls.text,
            fits=fits_context,
            seed_snapshots=seeds,
            # A rebuild decides nothing, and every proof it stores is read again at its
            # version before any later use: re-reading each pass's facts around each
            # call only spent its read budget (eight passes would take hundreds of
            # calls). Its authority is checked at every read and every model call.
            verify=None if self.setup.context_only else self.verify,
            language=self.setup.language,
            max_passes=self.context_passes,
            # A rebuild decides nothing: it interprets all it can afford.
            cover_all=self.setup.context_only,
        )
        return await self.context.build()

    async def verify(
        self, facts: tuple[DiscussionEvidence, ...], snapshots: tuple[SourceSnapshot, ...]
    ) -> None:
        """Read the selected facts again and check the run's authority.

        Args:
            facts: The selected facts.
            snapshots: The pages they were read on.

        Raises:
            InitiativeStopped: A fact changed or disappeared, or the authority refuses.
        """
        await revalidate_evidence(
            self.setup.claim, ContextResult(True, facts, (), snapshots), self.gateway
        )
        await self.authority.check()

    async def propose(self, result: ContextResult) -> OpeningDraft | None:
        """Decide and word an opening on a ready context, or abstain.

        The selected facts are read again before the decision and after the wording;
        an opening already made stops the run before its wording is paid for.

        Args:
            result: The context result.

        Returns:
            The draft, or None when the context is not ready or the decision is not to
            engage.

        Raises:
            InitiativeStopped: A fact was refused or changed, or the opening was
                already made.
        """
        if not result.ready:
            return None
        snapshots = await revalidate_evidence(self.setup.claim, result, self.gateway)
        current = await self.store.admit(snapshots)
        if len(current) != len(result.evidence):
            raise InitiativeStopped("evidence_refused")
        decision = await self._decide(result, current, snapshots)
        if not isinstance(decision, EngageDecision):
            self.reason = (
                "decision_defer" if isinstance(decision, DeferDecision) else "decision_skip"
            )
            return None
        selected = tuple(item for item in current if item.reference in decision.references)
        await self._refuse_repeated(selected, decision.topic)
        text = await self.model.message(self._wording(decision, selected))
        await revalidate_evidence(
            self.setup.claim,
            ContextResult(True, selected, result.knowledge, result.snapshots),
            self.gateway,
        )
        await self.authority.check()
        return make_draft(selected, decision, text)

    async def _decide(
        self,
        result: ContextResult,
        current: tuple[DiscussionEvidence, ...],
        snapshots: tuple[SourceSnapshot, ...],
    ) -> DiscussionDecision:
        """The decision model's verdict on the admitted facts; a deferral sets the retry."""
        async with get_db_context() as db:
            history = await relevant_opening_history(db, self.setup.claim.owner_id, current)
        payload = context_payload(
            now=datetime.now(UTC),
            rules=self.setup.controls.text,
            policy=self.policy,
            facts=current,
            knowledge=result.knowledge,
            snapshots=snapshots,
            history=history,
            language=self.setup.language,
        )
        decision = await self.model.decide(payload)
        validate_decision(
            decision,
            self.policy,
            snapshots,
            owner_id=self.setup.claim.owner_id,
            now=datetime.now(UTC),
        )
        if isinstance(decision, DeferDecision):
            self.retry_after = datetime.now(UTC) + timedelta(seconds=decision.retry_after_seconds)
        return decision

    async def _refuse_repeated(self, selected: tuple[DiscussionEvidence, ...], topic: str) -> None:
        """Stop before the wording is paid for: the commit would refuse this opening anyway."""
        async with get_db_context() as db:
            repeated = await DiscussionRepository(db).has_opening(
                self.setup.claim.owner_id, opening_fingerprint(selected, topic)
            )
        if repeated:
            raise InitiativeStopped("duplicate_opening")

    def _wording(self, decision: EngageDecision, selected: tuple[DiscussionEvidence, ...]) -> str:
        """The wording call's content: binding controls, identity, then the selection as data."""
        return (
            self.setup.controls.text
            + "\n"
            + json.dumps(
                {"language": self.setup.language, "personality": self.setup.personality},
                ensure_ascii=False,
            )
            + "\n"
            + wrap_external_content(
                json.dumps(
                    {
                        "decision": decision.model_dump(mode="json"),
                        "selected_evidence": [item.model_dump(mode="json") for item in selected],
                    },
                    ensure_ascii=False,
                ),
                "proactive_discussions/selected",
                "personal_evidence",
            )
        )

    async def publish(self, draft: OpeningDraft) -> None:
        """Publish the draft while the person's conversation is free, under the run's lease.

        Args:
            draft: The validated opening.

        Raises:
            InitiativeStopped: The spend is unreconciled, the authority refuses, or a
                turn holds the conversation.
        """
        if not self.permit.may_publish:
            raise InitiativeStopped("unreconciled_spend")
        await self.authority.check()
        async with get_db_context() as db:
            conversation = await ConversationService().get_or_create_conversation(
                self.setup.claim.owner_id, db, language=self.setup.language
            )
            conversation_id = str(conversation.id)
        redis = await get_redis_cache()
        token = str(self.setup.claim.run_id)
        async with active_run_lease(
            redis, conversation_id, run_id=token, stream_id=token
        ) as acquired:
            if not acquired:
                raise InitiativeStopped("conversation_busy")
            await self.authority.check(lease_owner=token)
            # The opening is an act of LIA's own: claimed before its message is
            # posted, settled from the commit that posts it (ADR-263).
            async with proactive_discussion_effect(
                user_id=self.setup.claim.owner_id, run_id=token
            ) as opened:
                async with get_db_context() as db:
                    receipt = await publication_repository(db).commit_opening(
                        self.setup.claim, draft, now=datetime.now(UTC), stats=self.stats
                    )
                opened.delivered = True
        self.published = receipt.opening_id


def opening_fingerprint(selected: tuple[DiscussionEvidence, ...], topic: str) -> str:
    """One opening's identity: the exact evidence versions it rests on, and its topic."""
    return semantic_version(
        tuple(
            sorted(
                semantic_version((item.source_account, item.object_id, item.version, topic))
                for item in selected
            )
        )
    )


def make_draft(
    selected: tuple[DiscussionEvidence, ...],
    decision: EngageDecision,
    text: str,
) -> OpeningDraft:
    """Assemble the opening draft: its fingerprint, proofs and privacy.

    It is private when the decision or a selected fact touches a sensitive topic,
    whatever the source the fact comes from: an SMS is personal data like a mail
    (ADR-357 amendment 2026-10-23).

    Args:
        selected: The facts the opening rests on.
        decision: The engagement.
        text: The opening's words.

    Returns:
        The draft.
    """
    return OpeningDraft(
        decision=decision,
        text=text,
        fingerprint=opening_fingerprint(selected, decision.topic),
        proofs=tuple(
            proof_of(item, {fact.reference: fact for fact in selected}, now=datetime.now(UTC))
            for item in selected
        ),
        sensitive_context=bool(
            decision.sensitive_topics or any(item.sensitive_topics for item in selected)
        ),
    )


def rule_cache_signature(controls: ControlSnapshot, policy: DiscussionPolicy) -> str:
    """What a compiled read restriction depends on: the controls, sources and prompt.

    Never the policy's revision counter: editing the hours recompiles nothing.

    Args:
        controls: The person's controls, as the run reads them.
        policy: The person's policy, whose consented sources the rules narrow.

    Returns:
        The signature the cached compilation is stored under.
    """
    return semantic_version(
        (
            "read-controls-v3",
            controls.revision,
            settings.discussion_context_prompt_version,
            json.dumps(policy.sources),
        )
    )


def _reason_of(error: Exception) -> RunReason:
    """Why an expected abstention stopped the run, in the run's closed vocabulary."""
    if isinstance(error, InitiativeStopped | DiscretionaryBudgetRefused):
        return error.reason
    if isinstance(error, UsageLimitExceededError):
        # A usage limit reached during the run refuses its next call: no provider
        # asked to wait, and the next tick asks the limit again before reading.
        return "usage_limit_reached"
    if isinstance(error, PromptBudgetExceeded):
        return "prompt_full"
    if isinstance(error, DirectiveBudgetExceeded):
        return "controls_over_budget"
    if isinstance(error, AuthorizationError):
        return "producer_disabled"
    return "failed"


async def run_for_owner(owner: UUID, *, rebuild_epoch: int | None = None) -> str:
    """One owner's run, counted whatever it ends on.

    Args:
        owner: The account served.
        rebuild_epoch: The context epoch of a requested rebuild, or None for
            an opening run.

    Returns:
        The run's outcome (``completed``, ``skipped``, ``failed``, or why it
        could not start).
    """
    outcome = "abandoned"
    try:
        outcome = await _run_for_owner(owner, rebuild_epoch=rebuild_epoch)
    except asyncio.CancelledError:
        raise
    except Exception:
        outcome = "error"
        raise
    finally:
        proactive_discussion_runs_total.labels(
            kind="opening" if rebuild_epoch is None else "rebuild", outcome=outcome
        ).inc()
    return outcome


async def _run_for_owner(owner: UUID, *, rebuild_epoch: int | None) -> str:
    if not settings.proactive_discussions_enabled:
        return "producer_disabled"
    limits = configured_limits()
    if limits is None:
        return "budget_unconfigured"
    setup = await _open_run(owner, limits, rebuild_epoch)
    if not isinstance(setup, DiscussionRunSetup):
        return setup

    async def issue(amount: Decimal, committed: Decimal) -> None:
        await issue_spend(setup.claim, amount, committed)

    permit = NativeSpendPermit(
        setup.reservation,
        issue=issue,
        context_calls=context_call_budget(context_only=setup.context_only),
    )
    act = DiscussionAct(setup, permit)
    # A cancellation leaves the run "abandoned"; every other exit is decided in _attempt.
    outcome: SettledRunState = "abandoned"
    try:
        outcome = await _attempt(act)
    finally:
        await asyncio.shield(_settle(act, outcome))
    if act.published is not None:
        await _deliver_now(owner, act.published)
    return outcome


async def _open_run(
    owner: UUID, limits: BudgetLimits, rebuild_epoch: int | None
) -> DiscussionRunSetup | RunNotStarted | Literal["controls_over_budget"]:
    """The run's claim and reservation, or why it cannot start."""
    try:
        setup = await initialize_run(owner, limits, rebuild_epoch=rebuild_epoch)
    except DirectiveBudgetExceeded:
        # ADR-359: rules that cannot all be read defer the run; never act on a part.
        logger.warning(
            "discussion_controls_over_budget",
            user_id=str(owner),
            rebuild=rebuild_epoch is not None,
        )
        return "controls_over_budget"
    return setup


async def _attempt(act: DiscussionAct) -> SettledRunState:
    """Run the act under its deadline: an expected abstention skips, a backoff defers.

    A rebuild has its own, longer deadline; reaching either one is a stop that says so
    (a rebuild cut short is served again and resumes), never a failure.
    """
    claim = act.setup.claim
    deadline = asyncio.timeout(
        settings.discussion_rebuild_deadline_seconds
        if act.setup.context_only
        else settings.discussion_run_deadline_seconds
    )
    try:
        async with deadline:
            return "completed" if await _generate_and_publish(act) else "skipped"
    except (
        InitiativeStopped,
        DiscretionaryBudgetRefused,
        UsageLimitExceededError,
        PromptBudgetExceeded,
        AuthorizationError,
        DirectiveBudgetExceeded,
    ) as exc:
        act.reason = _reason_of(exc)
        logger.info(
            "discussion_run_skipped",
            user_id=str(claim.owner_id),
            run_id=str(claim.run_id),
            reason=act.reason,
        )
        return "skipped"
    except Exception as exc:
        if isinstance(exc, TimeoutError) and deadline.expired():
            act.reason = "deadline_reached"
            logger.info(
                "discussion_run_skipped",
                user_id=str(claim.owner_id),
                run_id=str(claim.run_id),
                reason=act.reason,
            )
            return "skipped"
        # A provider's or a quota's backoff defers the run; anything else failed it.
        act.retry_after = retry_deadline(exc, now=datetime.now(UTC))
        act.reason = "provider_backoff" if act.retry_after is not None else "failed"
        logger.warning(
            "discussion_run_deferred" if act.retry_after is not None else "discussion_run_failed",
            user_id=str(claim.owner_id),
            run_id=str(claim.run_id),
            error_type=type(exc).__name__,
        )
        return "skipped" if act.retry_after is not None else "failed"


async def _settle(act: DiscussionAct, outcome: SettledRunState) -> None:
    """Close the reservation with what was really spent, then the run itself."""
    claim, permit = act.setup.claim, act.permit
    async with get_db_context() as db:
        await SpendRepository(db).settle(
            claim.owner_id, claim.run_id, actual=permit.actual_usd, uncertain=permit.uncertain
        )
    async with get_db_context() as db:
        await DiscussionRepository(db).settle_run(
            claim,
            status=outcome,
            now=datetime.now(UTC),
            retry_after=act.retry_after,
            reason=act.reason,
            stats=act.stats,
        )
    logger.info(
        "discussion_run_settled",
        user_id=str(claim.owner_id),
        run_id=str(claim.run_id),
        rebuild=act.setup.context_only,
        outcome=outcome,
        reason=act.reason,
        **(act.stats or {}),
    )


async def _deliver_now(owner: UUID, opening_id: UUID) -> None:
    """Deliver while the evidence proofs are fresh; the tick's sweep remains the fallback.

    Outside the run's deadline on purpose: the opening is committed, and a slow
    transport must neither fail the run nor wait for the rest of a batch, whose
    duration would outlive the delivery authority's proof window.
    """
    try:
        await dispatch_discussion(owner, opening_id)
    except Exception as exc:
        logger.warning(
            "discussion_delivery_failed",
            user_id=str(owner),
            opening_id=str(opening_id),
            error_type=type(exc).__name__,
        )


async def _generate_and_publish(act: DiscussionAct) -> bool:
    setup = act.setup
    run_id = str(setup.claim.run_id)
    # The run collects its own consultations, even when a chat turn launched it: every
    # source it opens is filed under its run, authored as the person's request when
    # it is a rebuild they asked for (ADR-263, ADR-359).
    with reads_requested_by_person(setup.context_only):
        async with consultation_collector(run_id):
            return await _act(act)


async def _act(act: DiscussionAct) -> bool:
    setup = act.setup
    async with out_of_turn_spend(
        str(setup.claim.run_id), setup.claim.owner_id, "proactive_discussions"
    ) as tracking:
        try:
            result = await act.build()
            act.reason, act.stats = result.outcome, result.stats
            draft = None if setup.context_only else await act.propose(result)
        finally:
            if act.stats is None and act.context is not None:
                # A build that stopped (a fact changed, a call failed) still says
                # what it had read and interpreted when it stopped.
                act.stats = act.context.tally.as_dict()
            receipts = tuple(
                ExternalReceipt.model_validate(row)
                for row in tracking.get_google_api_calls_breakdown()
            )
            act.permit.external_receipt(
                sum((row.cost_usd for row in receipts), Decimal(0)),
                uncertain=bool(act.paid_weather_reads and not receipts),
            )
        if setup.context_only:
            await act.authority.check()
            await act.store.complete_refresh()
            # A rebuild that could interpret nothing is no completed rebuild.
            return result.outcome not in NOTHING_INTERPRETED
        if draft is None:
            return False
        await act.publish(draft)
        act.reason = "published"
        return True
