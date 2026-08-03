"""Reminders API — cancelling one, by its own identifier.

The domain deliberately has no management surface: reminders are discrete and
ephemeral, created by conversation and deleted once fired. That design stands —
there is no listing endpoint here, no edit, no snooze.

What this adds is the one action the briefing card could not perform honestly.
The card showed a reminder and opened the chat; cancelling meant asking in
prose, and the agent path (`cancel_reminder_tool`) resolves its target through
the model, from a content substring. Two reminders worded alike, and the wrong
one goes.

Naming the reminder by its id removes the ambiguity entirely. The confirmation
does not disappear with the HITL draft — it moves to the card, as an
AlertDialog, exactly like deleting a routine: a deletion still asks before it
acts, it simply asks where the reader already is.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User

router = APIRouter(prefix="/reminders", tags=["Reminders"])


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
