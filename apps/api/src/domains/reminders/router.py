"""Reminders API: what is coming, and the reader's hand on it.

This surface was deliberately read-only. Reminders were "discrete and
ephemeral": created by conversation, deleted once fired, with no edit and no
listing that could grow into a management screen. That restraint was right for
a post-it, and `PendingReminderItem` still carries three fields.

**The owner reversed that decision on 2026-09-06** (see the ADR): a reminder
can now repeat, and a schedule someone configured once is a thing they must be
able to see and change without asking for it in prose. Creating, editing and
deleting are therefore first-class here.

What did NOT change: **the listing can never be a history.** A reminder is
deleted the moment it has no future left, a single occurrence after it fires
and a bounded series after its last instant, so there is nothing behind it to
list. The hub says so in its subtitle rather than showing an empty list a
reader would take for "nothing was ever sent".

Naming a reminder by its id is what makes deletion honest: the agent path
(`cancel_reminder_tool`) resolves its target from a content substring, and two
reminders worded alike send the wrong one.

**A fired reminder can be postponed** (ADR-268 amendment 2026-11-16). The ADR
first refused it because a press could not name WHICH occurrence it meant; every
occurrence that rings is now recorded (`reminder_firings`), and the three
`/firings/{firing_id}` routes act on that record — what the chat bubble offers,
a postponement (a one-shot copy, once), and stopping the series it came from.
A press is the person's own act: no model, no register row.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    RATE_LIMIT_REMINDER_FIRING_ACTIONS_PER_MINUTE,
    RECURRENCE_REMINDER_LIMITS,
)
from src.core.dependencies import get_db
from src.core.i18n import normalize_language
from src.core.session_dependencies import get_current_active_session
from src.core.time_utils import now_utc
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.reminders.firing_schemas import (
    ReminderFiringStateResponse,
    ReminderSnoozeRequest,
    ReminderSnoozeResponse,
    ReminderStopResponse,
)
from src.domains.reminders.firing_service import ReminderFiringService
from src.domains.reminders.firings import FiringSurface
from src.domains.reminders.read_models import (
    PendingReminderItem,
    PendingReminderPage,
    ReminderDetail,
    ReminderDetailPage,
)
from src.domains.reminders.schemas import ReminderCreate, ReminderUpdate
from src.domains.reminders.service import ReminderService
from src.domains.shared.display_query import DisplayQuery, display_query
from src.domains.users.models import User

router = APIRouter(prefix="/reminders", tags=["Reminders"])

rate_limit_firing_actions = create_user_rate_limiter(
    action="reminder_firing_action", max_calls=RATE_LIMIT_REMINDER_FIRING_ACTIONS_PER_MINUTE
)


@router.get(
    "",
    response_model=PendingReminderPage,
    summary="List the reminders that have not fired yet",
    description=(
        "One page of the caller's PENDING reminders, soonest first, with the "
        "exact total behind it. A fired reminder is deleted, so this lists the "
        "future — never a history of what was sent."
    ),
)
async def list_pending_reminders(
    limit: int = Query(default=10, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    criteria: DisplayQuery = Depends(display_query),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PendingReminderPage:
    """One page of the caller's pending reminders.

    Args:
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page and the EXACT total behind it.
    """
    reminders, total = await ReminderService(db).list_pending_page(
        user.id,
        limit=limit,
        offset=offset,
        criteria=criteria,
    )
    return PendingReminderPage(
        reminders=[PendingReminderItem.model_validate(r) for r in reminders],
        total=total,
        as_of=criteria.as_of,
    )


@router.get(
    "/detail",
    response_model=ReminderDetailPage,
    summary="List the caller's reminders with their schedules",
    description=(
        "The management view: every pending reminder with its recurrence, the "
        "sentence describing it, and the instants it will fire at. Declared "
        "BEFORE `/{reminder_id}` so the literal path is not swallowed by it."
    ),
)
async def list_reminder_details(
    limit: int = Query(default=25, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderDetailPage:
    """One page of the caller's reminders, schedules included.

    Args:
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page and the exact total behind it.
    """
    reminders, total = await ReminderService(db).list_pending_page(
        user.id, limit=limit, offset=offset
    )
    language = normalize_language(user.language)
    return ReminderDetailPage(
        reminders=[ReminderDetail.of(r, language) for r in reminders],
        total=total,
    )


@router.post(
    "",
    response_model=ReminderDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a reminder",
    description=(
        "Create a reminder from a recurrence. Omitting the recurrence means "
        "once, derived from the instant - the same rule the migration applied "
        "to reminders that predate schedules."
    ),
)
async def create_reminder(
    payload: ReminderCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderDetail:
    """Create one reminder for the caller.

    The cap is INJECTED rather than owned by the recurrence model: a routine
    may fire 12 times a day and a reminder 48, and the engine serves both
    because the ceiling travels with the caller.

    Args:
        payload: What to remind, when, and how often.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The created reminder, schedule included.

    Raises:
        RecurrenceError: The recurrence exceeds what a REMINDER may ask.
    """
    if payload.recurrence is not None:
        payload.recurrence.validate_against(RECURRENCE_REMINDER_LIMITS)
    timezone = user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    reminder = await ReminderService(db).create_reminder(user.id, payload, timezone)
    await db.commit()
    return ReminderDetail.of(reminder, normalize_language(user.language))


@router.get(
    "/firings/{firing_id}",
    response_model=ReminderFiringStateResponse,
    summary="What a fired reminder offers",
    description=(
        "The occurrence that rang: until when it can be postponed, where a press "
        "already put it, and whether its reminder has a future to stop. An unknown, "
        "purged or foreign occurrence answers 404 alike."
    ),
)
async def get_reminder_firing(
    firing_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderFiringStateResponse:
    """The state of one fired occurrence the caller owns.

    Args:
        firing_id: The occurrence the notification named.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        What its bubble offers.

    Raises:
        ResourceNotFoundError: Unknown, purged, or another account's occurrence.
    """
    state = await ReminderFiringService(db).state(firing_id, user.id, now=now_utc())
    return ReminderFiringStateResponse.of(state)


@router.post(
    "/firings/{firing_id}/snooze",
    response_model=ReminderSnoozeResponse,
    dependencies=[Depends(rate_limit_firing_actions)],
    summary="Postpone a fired reminder",
    description=(
        "Bring the occurrence back in a short or long delay, or tomorrow morning on "
        "the account's wall clock: a one-shot copy, created once whatever the number "
        "of presses. The outcome says when it comes back, that the window closed, or "
        "that the series already rings again before that instant."
    ),
)
async def snooze_reminder_firing(
    firing_id: UUID,
    payload: ReminderSnoozeRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderSnoozeResponse:
    """Postpone one fired occurrence the caller owns.

    Args:
        firing_id: The occurrence the notification named.
        payload: Which « later », and where the press came from.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The verdict and the instants it rests on.

    Raises:
        ResourceNotFoundError: Unknown, purged, or another account's occurrence.
    """
    result = await ReminderFiringService(db).snooze(
        firing_id,
        user.id,
        payload.choice,
        zone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        now=now_utc(),
        surface=payload.surface,
    )
    await db.commit()
    return ReminderSnoozeResponse.of(result)


@router.post(
    "/firings/{firing_id}/stop",
    response_model=ReminderStopResponse,
    dependencies=[Depends(rate_limit_firing_actions)],
    summary="Stop the reminder a fired occurrence came from",
    description=(
        "Delete the repeating reminder this occurrence belongs to: it will not ring "
        "again. A reminder already gone, or one with no future left, answers "
        "already_stopped."
    ),
)
async def stop_reminder_firing(
    firing_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderStopResponse:
    """Stop the series behind one fired occurrence the caller owns.

    Args:
        firing_id: The occurrence the notification named.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        Stopped, or already stopped.

    Raises:
        ResourceNotFoundError: Unknown, purged, or another account's occurrence.
    """
    outcome = await ReminderFiringService(db).stop(
        firing_id, user.id, now=now_utc(), surface=FiringSurface.CHAT
    )
    await db.commit()
    return ReminderStopResponse(outcome=outcome)


@router.patch(
    "/{reminder_id}",
    response_model=ReminderDetail,
    summary="Change a reminder",
    description=(
        "Change what a reminder says or when it fires. The recurrence is "
        "replaced WHOLE; omitting it leaves the schedule alone and sending it "
        "as null is refused."
    ),
)
async def update_reminder(
    reminder_id: UUID,
    payload: ReminderUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReminderDetail:
    """Change one reminder the caller owns.

    Args:
        reminder_id: The reminder to change.
        payload: The fields to change.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The updated reminder.

    Raises:
        ResourceNotFoundError: Unknown id, or one belonging to another account.
            The service reads the row then compares its owner and raises the
            SAME error either way, so the endpoint cannot be used to probe for
            someone else's reminders.
        ResourceConflictError: The reminder is already being processed.
        RecurrenceError: The recurrence exceeds what a REMINDER may ask.
    """
    if payload.recurrence is not None:
        payload.recurrence.validate_against(RECURRENCE_REMINDER_LIMITS)
    timezone = user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    reminder = await ReminderService(db).update_reminder(
        reminder_id=reminder_id, user_id=user.id, data=payload, user_timezone=timezone
    )
    await db.commit()
    return ReminderDetail.of(reminder, normalize_language(user.language))


@router.delete(
    "/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a pending reminder",
    description=(
        "Cancel the reminder with this id. A reminder belonging to another "
        "account answers exactly like a missing one, so the endpoint cannot be "
        "used to probe for someone else's reminders."
    ),
)
async def cancel_reminder(
    reminder_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel one reminder the caller owns.

    Args:
        reminder_id: The reminder to cancel.
        user: Authenticated session owner.
        db: Request-scoped session.

    Raises:
        ResourceNotFoundError: Unknown id, or one belonging to another account.
            ``ReminderService.get_by_id`` reads the row then compares its owner
            and raises the SAME error either way, so the two cases are
            indistinguishable from outside and the endpoint cannot be used to
            probe for someone else's reminders.
        ResourceConflictError: Already fired or already cancelled.
    """
    await ReminderService(db).cancel_reminder(reminder_id=reminder_id, user_id=user.id)
    await db.commit()
