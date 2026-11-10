"""The proposal handlers habits owns: the ones that touch routines (ADR-375).

``automate_need`` creates an ordinary time routine — its title and instruction
come from ``core.i18n_habit_routines`` in the person's language and are theirs
from then on (editable like any routine they wrote). ``shift_routine`` moves the
ONE time the proposal named, and refuses when that time is no longer there.
``fix_routine`` and ``connect_source`` change nothing: accepting opens the
routine or the connectors, and the card follows the result.

Every routine write goes through ``ScheduledActionService`` — its owner lock,
its cap and its re-arming — never a second door. Installed at import; the boot
installs again before asserting the registry complete (ADR-270).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.core.i18n_habit_routines import routine_copy
from src.core.recurrence import RecurrenceSpec, TimeOfDay
from src.core.time_utils import resolve_user_timezone
from src.domains.habits.models import HabitProposal, ProposalKind
from src.domains.habits.proposal_actions import (
    ProposalActionRefused,
    ProposalActionResult,
    ProposalRefusal,
    install_proposal_action,
)
from src.domains.habits.proposal_facts import (
    AutomateNeedFacts,
    ConnectSourceFacts,
    FixRoutineFacts,
    ShiftRoutineFacts,
)
from src.domains.scheduled_actions.errors import RoutineLimitError
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.schemas import ScheduledActionCreate, ScheduledActionUpdate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

#: ISO weekdays of a working-days cadence.
_WORKING_DAYS = (1, 2, 3, 4, 5)


def need_recurrence(facts: AutomateNeedFacts, *, start: datetime) -> RecurrenceSpec:
    """The schedule serving a need: its days, the hour it is ready by.

    Args:
        facts: The proposal's facts.
        start: Now, in the person's timezone (the series starts that day).

    Returns:
        A daily schedule, or a weekly one on the working days or on the need's
        weekday.
    """
    shape: dict[str, object] = {
        "times": {"mode": "at", "at": [{"hour": facts.hour, "minute": facts.minute}]},
        "anchor_date": start.date(),
    }
    if facts.cadence == "weekdays":
        return RecurrenceSpec.model_validate(
            {**shape, "freq": "weekly", "byweekday": _WORKING_DAYS}
        )
    if facts.cadence == "weekly" and facts.weekday is not None:  # the facts name it
        days = (facts.weekday + 1,)
        return RecurrenceSpec.model_validate({**shape, "freq": "weekly", "byweekday": days})
    return RecurrenceSpec.model_validate({**shape, "freq": "daily"})


async def _owned_routine(
    service: ScheduledActionService, raw_id: str, user_id: UUID
) -> ScheduledAction:
    """The routine a proposal names, still the person's — refused when gone."""
    try:
        return await service.get_with_ownership_check(UUID(raw_id), user_id)
    except ValueError, ResourceNotFoundError:
        raise ProposalActionRefused(ProposalRefusal.ROUTINE_GONE) from None


async def automate_need(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Create the routine that has the need ready before the person asks.

    Args:
        db: The decision's session.
        user: The person accepting.
        proposal: The claimed proposal.

    Returns:
        The routine created.

    Raises:
        ProposalActionRefused: When the account already holds its maximum of
            routines.
    """
    facts = AutomateNeedFacts.model_validate(proposal.payload)
    tz = resolve_user_timezone(user)
    title, instruction = routine_copy(
        facts.domain, "week" if facts.cadence == "weekly" else "day", user.language
    )
    data = ScheduledActionCreate(
        title=title,
        action_prompt=instruction,
        recurrence=need_recurrence(facts, start=datetime.now(tz)),
    )
    try:
        routine = await ScheduledActionService(db).create(user.id, data, str(tz))
    except RoutineLimitError:
        raise ProposalActionRefused(ProposalRefusal.ROUTINE_LIMIT) from None
    return ProposalActionResult(routine_id=routine.id)


async def shift_routine(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Move the planned time the person keeps overriding by hand.

    Args:
        db: The decision's session.
        user: The person accepting.
        proposal: The claimed proposal.

    Returns:
        The routine moved.

    Raises:
        ProposalActionRefused: When the routine is gone, or the time the
            proposal named is no longer one of its listed times.
    """
    facts = ShiftRoutineFacts.model_validate(proposal.payload)
    service = ScheduledActionService(db)
    routine = await _owned_routine(service, facts.routine_id, user.id)
    spec = routine.recurrence_spec
    moved = TimeOfDay(hour=facts.from_hour, minute=facts.from_minute)
    if spec is None or spec.times.mode != "at" or moved not in spec.times.at:
        raise ProposalActionRefused(ProposalRefusal.ROUTINE_CHANGED)
    times = [time for time in spec.times.at if time != moved]
    times.append(TimeOfDay(hour=facts.hour, minute=facts.minute))
    shifted = RecurrenceSpec.model_validate(
        {
            **spec.model_dump(mode="json"),
            "times": {"mode": "at", "at": [time.model_dump() for time in times]},
        }
    )
    await service.update(routine.id, user.id, ScheduledActionUpdate(recurrence=shifted))
    return ProposalActionResult(routine_id=routine.id)


async def open_routine(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Point at the failing routine — the person fixes it on its own screen.

    Args:
        db: The decision's session.
        user: The person accepting.
        proposal: The claimed proposal.

    Returns:
        The routine to open.

    Raises:
        ProposalActionRefused: When the routine is gone.
    """
    facts = FixRoutineFacts.model_validate(proposal.payload)
    routine = await _owned_routine(ScheduledActionService(db), facts.routine_id, user.id)
    return ProposalActionResult(routine_id=routine.id)


async def open_connectors(
    db: AsyncSession, user: User, proposal: HabitProposal
) -> ProposalActionResult:
    """Nothing to write: the card opens the connectors of the category it names.

    Args:
        db: The decision's session (unused).
        user: The person accepting (unused).
        proposal: The claimed proposal (its facts are checked).

    Returns:
        An empty result.
    """
    ConnectSourceFacts.model_validate(proposal.payload)
    return ProposalActionResult()


def install() -> None:
    """Register the four handlers habits owns."""
    install_proposal_action(ProposalKind.AUTOMATE_NEED, automate_need)
    install_proposal_action(ProposalKind.SHIFT_ROUTINE, shift_routine)
    install_proposal_action(ProposalKind.FIX_ROUTINE, open_routine)
    install_proposal_action(ProposalKind.CONNECT_SOURCE, open_connectors)


install()
