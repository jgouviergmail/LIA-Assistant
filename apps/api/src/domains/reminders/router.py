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
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    RECURRENCE_REMINDER_LIMITS,
    REMINDER_OCCURRENCES_PREVIEW,
)
from src.core.dependencies import get_db
from src.core.i18n import DEFAULT_LANGUAGE
from src.core.recurrence import RecurrenceSpec, describe, occurrences
from src.core.session_dependencies import get_current_active_session
from src.core.time_utils import now_utc
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderCreate, ReminderUpdate
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User

router = APIRouter(prefix="/reminders", tags=["Reminders"])


class PendingReminderItem(BaseModel):
    """One reminder that has not fired yet, as the HUB reads it.

    Deliberately thin, and still so: the hub shows what is coming and offers a
    cancel. The management screen reads `ReminderDetail` below, which carries
    the schedule. Keeping the two apart stops a badge count from paying for a
    recurrence description it never renders.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="The reminder — the id the cancel route takes.")
    content: str = Field(description="What the reader asked to be reminded of.")
    trigger_at: datetime = Field(description="UTC instant it will fire.")


class PendingReminderPage(BaseModel):
    """One page of pending reminders, and the EXACT total behind it.

    This can never be a history: a reminder is DELETED once notified, so the
    only thing there is to list is the future (ADR-185 for the total).
    """

    reminders: list[PendingReminderItem]
    total: int = Field(ge=0, description="Exact count of reminders still waiting.")


class ReminderDetail(BaseModel):
    """One reminder, as the MANAGEMENT screen reads it.

    Everything the hub item carries, plus what a reader needs to understand and
    change a schedule: the recurrence itself, the sentence the server composed
    for it, and the instants it will actually fire at.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    trigger_at: datetime = Field(description="UTC instant of the NEXT firing.")
    user_timezone: str = Field(description="IANA zone the wall clock is read in.")
    recurrence: RecurrenceSpec
    schedule_display: str = Field(default="", description="The schedule, in the reader's words.")
    times_of_day: list[str] = Field(default_factory=list, description="`HH:MM`, ascending.")
    runs_per_day: int = Field(default=0, description="Most times a served day fires.")
    next_occurrences: list[datetime] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def of(cls, reminder: Reminder, language: str) -> ReminderDetail:
        """Render one reminder for the management screen.

        The derived fields are computed HERE rather than stored: a schedule
        sentence held in a column would be right in one language and stale in
        the other five.

        Args:
            reminder: The row to render.
            language: The reader's language, for the sentence.

        Returns:
            The rendered reminder.
        """
        spec = reminder.recurrence_spec
        return cls(
            id=reminder.id,
            content=reminder.content,
            trigger_at=reminder.trigger_at,
            user_timezone=reminder.user_timezone,
            recurrence=spec,
            schedule_display=describe(spec, language),
            times_of_day=[f"{m.hour:02d}:{m.minute:02d}" for m in spec.times.materialise()],
            runs_per_day=spec.per_day(),
            next_occurrences=occurrences(
                spec,
                reminder.user_timezone,
                after=now_utc(),
                count=REMINDER_OCCURRENCES_PREVIEW,
            ),
            created_at=reminder.created_at,
        )


class ReminderDetailPage(BaseModel):
    """One page of the caller's reminders, and the EXACT total behind it."""

    reminders: list[ReminderDetail]
    total: int = Field(ge=0, description="Exact count of reminders still waiting.")


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
        user.id, limit=limit, offset=offset
    )
    return PendingReminderPage(
        reminders=[PendingReminderItem.model_validate(r) for r in reminders],
        total=total,
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
    language = user.language or DEFAULT_LANGUAGE
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
    return ReminderDetail.of(reminder, user.language or DEFAULT_LANGUAGE)


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
    return ReminderDetail.of(reminder, user.language or DEFAULT_LANGUAGE)


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
