"""Reminders API — reading what is still coming, and cancelling one by id.

The domain deliberately has no MANAGEMENT surface: reminders are discrete and
ephemeral, created by conversation and deleted once fired. That design stands —
no edit, no snooze, no acknowledgement, and the listing below is read-only and
forward-looking by construction.

**The listing can never be a history.** A reminder is deleted the instant it
fires, so there is nothing behind it to list; the hub says so in its subtitle
rather than showing an empty list a reader would read as "nothing was ever
sent". `PendingReminderItem` carries three fields on purpose: the ones an edit
or a snooze would need are absent, so this surface cannot drift into the
management UI the domain refuses.

The cancel route below is the one action the briefing card could not perform
honestly.
The card showed a reminder and opened the chat; cancelling meant asking in
prose, and the agent path (`cancel_reminder_tool`) resolves its target through
the model, from a content substring. Two reminders worded alike, and the wrong
one goes.

Naming the reminder by its id removes the ambiguity entirely. The confirmation
does not disappear with the HITL draft — it moves to the card, as an
AlertDialog, exactly like deleting a routine: a deletion still asks before it
acts, it simply asks where the reader already is.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User

router = APIRouter(prefix="/reminders", tags=["Reminders"])


class PendingReminderItem(BaseModel):
    """One reminder that has not fired yet.

    Deliberately thin: the hub shows what is coming and offers the cancel that
    already existed. No editing, no snoozing, no acknowledgement — the fields
    those would need are absent so the surface cannot drift into the management
    UI the domain refuses.
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
