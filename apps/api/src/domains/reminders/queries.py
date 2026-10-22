"""The owned pending set shared by management and bounded context projections."""

from uuid import UUID

from sqlalchemy import Select, select

from src.domains.reminders.models import Reminder, ReminderStatus


def pending_reminders(user_id: UUID) -> Select[tuple[Reminder]]:
    """Select an account's pending reminders: the set management and context share.

    Args:
        user_id: The account.

    Returns:
        The selection.
    """
    return select(Reminder).where(
        Reminder.user_id == user_id, Reminder.status == ReminderStatus.PENDING.value
    )
