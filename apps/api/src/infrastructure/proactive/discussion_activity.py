"""What the settings page shows of the producer: its last runs, their cost, a ceiling reached.

Every figure is read where it is decided: the run rows say whether a rebuild is
running, how the last runs ended and which one last updated the context; each
run's own ``message_token_summary`` row says what it cost (the chat meter's
ledger, ADR-272); and the predicates a run asks before it starts say whether a
ceiling stops the next one — the usage limit every model call asks, then the
reservation's own. Amounts are never shown: a person needs to know THAT a
ceiling stops LIA, not by how many cents.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import normalize_language
from src.domains.chat.models import MessageTokenSummary
from src.domains.proactive_discussions.api_schemas import (
    BudgetState,
    CeilingReached,
    DiscussionActivity,
    RebuildObstacle,
    RunStats,
    RunSummary,
    RunUsage,
)
from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.finance_repository import (
    BudgetAvailability,
    SpendRepository,
    utc_day_end,
)
from src.domains.proactive_discussions.models import DiscussionPreference, DiscussionRun
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.shared.discussion_directives import DirectiveBudgetExceeded
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.infrastructure.proactive.discussion_control import ControlSnapshot, preview_controls
from src.infrastructure.proactive.discussion_run_setup import configured_limits, first_call_bound


async def read_activity(db: AsyncSession, owner: UUID, *, now: datetime) -> DiscussionActivity:
    """The producer's state for one account.

    Args:
        db: A read session.
        owner: The account whose activity is shown.
        now: The clock (a lease past its end is no longer a running rebuild).

    Returns:
        The rebuild's state, the obstacle that holds it when the server knows
        one, the last rebuild, the last run that updated the context and the last
        run, each with its cost, and the first ceiling that stops a run now.
    """
    requested = bool(
        await db.scalar(
            select(ContextStateRecord.refresh_requested).where(ContextStateRecord.user_id == owner)
        )
    )
    running = await _rebuild_running(db, owner, now=now)
    controls = await _controls(db, owner, now=now)
    budget = await _budget(db, owner, controls, now=now)
    settled = DiscussionRun.settled_at.is_not(None)
    return DiscussionActivity(
        rebuild="running" if running else "requested" if requested else "idle",
        obstacle=_obstacle(requested and not running, controls, budget),
        last_rebuild=await _latest(db, owner, DiscussionRun.context_only.is_(True)),
        last_update=await _latest(
            db, owner, settled, DiscussionRun.stats["context_updates"].as_integer() > 0
        ),
        last_run=await _latest(db, owner, settled),
        budget=budget,
    )


def _obstacle(
    waiting: bool, controls: ControlSnapshot | None, budget: BudgetState
) -> RebuildObstacle | None:
    """Why a requested rebuild that is not running cannot start, when the server knows."""
    if not waiting:
        return None
    if controls is None:
        return "controls_over_budget"
    return "ceiling_reached" if budget.reached is not None else None


async def _controls(db: AsyncSession, owner: UUID, *, now: datetime) -> ControlSnapshot | None:
    """The controls a run would read now, or None when they exceed their budget."""
    try:
        return await preview_controls(db, owner, now=now)
    except DirectiveBudgetExceeded:
        return None


async def _rebuild_running(db: AsyncSession, owner: UUID, *, now: datetime) -> bool:
    lease = (
        await db.execute(
            select(DiscussionPreference.active_run_id, DiscussionPreference.lease_until).where(
                DiscussionPreference.user_id == owner
            )
        )
    ).one_or_none()
    if lease is None or lease.active_run_id is None or lease.lease_until is None:
        return False
    if lease.lease_until <= now:
        return False
    return bool(
        await db.scalar(
            select(DiscussionRun.context_only).where(
                DiscussionRun.user_id == owner, DiscussionRun.id == lease.active_run_id
            )
        )
    )


async def _latest(
    db: AsyncSession, owner: UUID, *conditions: ColumnElement[bool]
) -> RunSummary | None:
    """The account's latest run meeting ``conditions``, with its own ledger row's cost."""
    run = await db.scalar(
        select(DiscussionRun)
        .where(DiscussionRun.user_id == owner, *conditions)
        .order_by(DiscussionRun.claimed_at.desc(), DiscussionRun.id.desc())
        .limit(1)
    )
    if run is None:
        return None
    summary = await db.scalar(
        select(MessageTokenSummary).where(
            MessageTokenSummary.user_id == owner, MessageTokenSummary.run_id == str(run.id)
        )
    )
    return RunSummary.model_validate(
        {
            "kind": "rebuild" if run.context_only else "opening",
            "state": run.state,
            "claimed_at": run.claimed_at,
            "settled_at": run.settled_at,
            "reason": run.reason,
            "stats": _stats(run.stats),
            "usage": (
                None
                if summary is None
                else RunUsage(
                    tokens_in=summary.total_prompt_tokens,
                    tokens_out=summary.total_completion_tokens,
                    tokens_cache=summary.total_cached_tokens,
                    google_requests=summary.google_api_requests,
                    cost_eur=float(summary.billed_cost_eur),
                )
            ),
        }
    )


def _stats(value: dict[str, object] | None) -> RunStats | None:
    """A run row's counts, or None for a run settled before they were recorded."""
    if value is None:
        return None
    try:
        return RunStats.model_validate(value)
    except ValidationError:
        return None


async def _budget(
    db: AsyncSession, owner: UUID, controls: ControlSnapshot | None, *, now: datetime
) -> BudgetState:
    """The first ceiling that stops a run now, in the order a run meets them.

    The usage limit first — the verdict every model call asks
    (``enforce_usage_limit``) and the one a run asks before reading
    (``initialize_run``) — then the reservation's own predicate.
    """
    limits = configured_limits()
    if limits is None:
        return BudgetState(configured=False)
    usage = await UsageLimitService.check_user_allowed(owner)
    if not usage.allowed:
        paused = usage.status is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET
        return BudgetState(
            configured=True,
            reached="instance_budget" if paused else "usage_limit",
            # The deployment's budget renews with the UTC day; a person's usage
            # limit renews with their own cycle, which only its administrator sets.
            resets_at=utc_day_end(now) if paused else None,
        )
    minimum = Decimal(0)
    if controls is not None:
        policy = await DiscussionRepository(db).get_policy(owner)
        language = normalize_language(
            await db.scalar(select(User.language).where(User.id == owner))
        )
        minimum = first_call_bound(controls.text, policy, language, now=now)
    availability = await SpendRepository(db).availability(
        owner, limits=limits, now=now, minimum=minimum
    )
    reached = _day_ceiling(availability)
    return BudgetState(
        configured=True,
        reached=reached,
        resets_at=availability.resets_at if reached in ("owner_day", "instance_day") else None,
    )


def _day_ceiling(availability: BudgetAvailability) -> CeilingReached | None:
    """The reservation's ceiling that stops a run now: the run's first, no day fixes it."""
    if availability.run_insufficient:
        return "run_ceiling"
    if not availability.owner_available:
        return "owner_day"
    if not availability.instance_available:
        return "instance_day"
    return None
