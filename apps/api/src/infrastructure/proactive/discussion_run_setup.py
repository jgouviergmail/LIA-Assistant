"""Claim and financial reservation commit before any source or model call."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.i18n import normalize_language
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.personalities.service import PersonalityService
from src.domains.proactive_discussions.contextualization.loop import context_payload
from src.domains.proactive_discussions.finance_permit import (
    DiscretionaryBudgetRefused,
    upper_model_cost,
)
from src.domains.proactive_discussions.finance_repository import (
    BudgetLimits,
    SpendRepository,
    SpendReservation,
    utc_day_end,
)
from src.domains.proactive_discussions.llm_contracts import (
    ContextInterpretation,
    PromptBudgetExceeded,
)
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.discussion_attention import attention_available
from src.infrastructure.proactive.discussion_control import ControlSnapshot, load_controls
from src.infrastructure.proactive.discussion_llm import prepare_call

#: Why a run could not start: nothing may start now, today cannot fund its first call,
#: or the person's usage limit (or the instance's daily budget) refuses every model call.
RunNotStarted = Literal["ineligible", "budget_exhausted", "usage_limit_reached"]


@dataclass(frozen=True)
class DiscussionRunSetup:
    """What a claimed, funded run holds: claim, policy, controls, reservation, voice.

    ``context_only`` marks a rebuild the person asked for.
    """

    claim: RunClaim
    policy: DiscussionPolicy
    controls: ControlSnapshot
    reservation: SpendReservation
    language: str
    personality: str
    context_only: bool = False


def configured_limits() -> BudgetLimits | None:
    """Return the three operator ceilings, or None while one is unset (nothing starts)."""
    owner, instance, run = (
        settings.discussion_owner_daily_budget_usd,
        settings.discussion_instance_daily_budget_usd,
        settings.discussion_run_budget_usd,
    )
    if owner is None or instance is None or run is None:
        return None
    return BudgetLimits(owner_daily=owner, instance_daily=instance, run_max=run)


def first_call_bound(
    rules: str, policy: DiscussionPolicy, language: str, *, now: datetime
) -> Decimal:
    """The most a run's first model call can cost: a context call on the rules alone.

    It is priced on the configured context slot and its tariff, like every call the
    permit admits (ADR-360). A run needs room for it to start; less room is no run.

    Args:
        rules: The person's complete controls, as every context call carries them.
        policy: The person's policy.
        language: The person's language.
        now: The clock the payload states.

    Returns:
        The bound in USD; zero when the call could not be prepared or priced, so
        the run starts and its first admission refuses with the actual reason.
    """
    payload = context_payload(
        now=now,
        rules=rules,
        policy=policy,
        facts=(),
        knowledge=(),
        snapshots=(),
        language=language,
        research_waves=max(0, settings.discussion_context_calls_per_run - 1),
    )
    try:
        call = prepare_call("context", payload, ContextInterpretation)
        return upper_model_cost(call.config, call.input_tokens)
    except PromptBudgetExceeded, DiscretionaryBudgetRefused:
        return Decimal(0)


async def initialize_run(
    owner: UUID, limits: BudgetLimits, *, rebuild_epoch: int | None = None
) -> DiscussionRunSetup | RunNotStarted:
    """Claim the account and reserve the run's allowance, before any source or model call.

    The operator's switch must be on and, for an opening run, the person's attention
    free; the controls are read first, which also settles the replies to the
    previous opening. A usage limit that refuses the person's model calls settles
    the claim as skipped before any source is read — every call would be refused,
    and a paid read (the weather) would be spent for nothing; the next tick asks
    again, so a limit lifted by an administrator resumes at once. The run reserves
    its ceiling or what is left of the day, whichever is smaller; a day that cannot
    fund its first call settles the claim as skipped and defers the account to the
    UTC day's end, so no tick claims it again for nothing before the allowance
    comes back.

    Args:
        owner: The account.
        limits: The configured ceilings.
        rebuild_epoch: The context epoch of a requested rebuild, or None for an
            opening run.

    Returns:
        The run's setup, or why it did not start.

    Raises:
        DirectiveBudgetExceeded: The controls do not fit their budget.
    """
    async with get_db_context() as db:
        try:
            await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
        except AuthorizationError:
            return "ineligible"
        # Control replies settle the old opening before the pending-opening gate.
        controls = await load_controls(db, owner, now=datetime.now(UTC))
        if rebuild_epoch is None and not await attention_available(
            db, owner, now=datetime.now(UTC)
        ):
            return "ineligible"
        repo = DiscussionRepository(db)
        claim = await repo.claim_run(
            owner,
            now=datetime.now(UTC),
            lease_seconds=settings.discussion_run_lease_seconds,
            rebuild_epoch=rebuild_epoch,
        )
        if claim is None:
            return "ineligible"
        if await UsageLimitService.is_user_blocked_for_llm(owner, layer="proactive_discussions"):
            await repo.settle_run(
                claim, status="skipped", now=datetime.now(UTC), reason="usage_limit_reached"
            )
            return "usage_limit_reached"
        policy = await repo.get_policy(owner)
        language = normalize_language(
            await db.scalar(select(User.language).where(User.id == owner))
        )
        now = datetime.now(UTC)
        reservation = await SpendRepository(db).reserve(
            claim,
            estimate=limits.run_max,
            limits=limits,
            now=now,
            minimum=first_call_bound(controls.text, policy, language, now=now),
        )
        if reservation in ("no_room", "ceiling_too_low"):
            # Checked again when the UTC day turns, or at once after a settings edit or
            # a rebuild request (both move what the retry is conditioned on).
            await repo.settle_run(
                claim,
                status="skipped",
                now=now,
                retry_after=utc_day_end(now),
                reason="budget_exhausted" if reservation == "no_room" else "run_ceiling_too_low",
            )
            return "budget_exhausted"
        if isinstance(reservation, str):
            await repo.settle_run(claim, status="skipped", now=now, reason="stale_claim")
            return "ineligible"
        personality = await PersonalityService(db).get_prompt_instruction_for_user(owner) or ""
        return DiscussionRunSetup(
            claim, policy, controls, reservation, language, personality, rebuild_epoch is not None
        )


async def issue_spend(claim: RunClaim, amount: Decimal, committed: Decimal) -> None:
    """Issue one paid call's upper bound against the run's reservation, before the call.

    Args:
        claim: The run's claim.
        amount: The call's upper cost, in USD.
        committed: What the run has committed before this call, in USD.

    Raises:
        AuthorizationError: The operator switched the capability off.
        DiscretionaryBudgetRefused: The reservation no longer authorises spending.
    """
    async with get_db_context() as db:
        await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
        if not await SpendRepository(db).issue(
            claim, amount=amount, now=datetime.now(UTC), committed=committed
        ):
            # The hold refused (claim lost, day over, room spent): the run abstains,
            # it did not fail, and what it already spent is settled as usual.
            raise DiscretionaryBudgetRefused(
                "reservation_refused",
                "discussion financial reservation no longer authorizes spending",
            )
