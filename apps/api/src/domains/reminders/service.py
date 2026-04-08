"""
Reminder service for business logic.

Pattern: Follows PersonalityService structure.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.repository import ReminderRepository
from src.domains.reminders.schemas import ReminderCreate

logger = structlog.get_logger(__name__)


def convert_to_utc(local_dt: datetime, user_timezone: str) -> datetime:
    """
    Convert a local datetime to UTC.

    Args:
        local_dt: Datetime in user's local timezone (may be naive or aware)
        user_timezone: IANA timezone string (e.g., 'Europe/Paris')

    Returns:
        Datetime in UTC with timezone info
    """
    tz = ZoneInfo(user_timezone)

    # If datetime is naive, interpret it as being in user's timezone
    if local_dt.tzinfo is None:
        local_aware = local_dt.replace(tzinfo=tz)
    else:
        # If already aware, convert to the specified timezone first
        local_aware = local_dt.astimezone(tz)

    # Convert to UTC
    return local_aware.astimezone(UTC)


class ReminderService:
    """Service for reminder management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ReminderRepository(db)

    async def get_by_id(self, reminder_id: UUID, user_id: UUID) -> Reminder:
        """
        Get reminder by ID with user ownership check.

        Raises:
            ResourceNotFoundError: If reminder doesn't exist or belongs to another user
        """
        reminder = await self.repository.get_by_id(reminder_id)
        if not reminder or reminder.user_id != user_id:
            raise ResourceNotFoundError("reminder", str(reminder_id))
        return reminder

    async def create_reminder(
        self,
        user_id: UUID,
        data: ReminderCreate,
        user_timezone: str,
    ) -> Reminder:
        """
        Create a new reminder with UTC conversion.

        Args:
            user_id: ID of the user creating the reminder
            data: Reminder creation data with local trigger time
            user_timezone: User's timezone for conversion

        Returns:
            Created reminder instance
        """
        # Convert local time to UTC
        trigger_at_utc = convert_to_utc(data.trigger_at, user_timezone)

        # Validate trigger time is in the future
        now_utc = datetime.now(UTC)
        if trigger_at_utc <= now_utc:
            # Allow a small grace period (30 seconds) for "in 1 minute"
            logger.warning(
                "reminder_trigger_in_past",
                trigger_at=trigger_at_utc.isoformat(),
                now=now_utc.isoformat(),
            )

        reminder = await self.repository.create(
            {
                "user_id": user_id,
                "content": data.content,
                "original_message": data.original_message,
                "trigger_at": trigger_at_utc,
                "user_timezone": user_timezone,
                "status": ReminderStatus.PENDING.value,
            }
        )

        logger.info(
            "reminder_created",
            reminder_id=str(reminder.id),
            user_id=str(user_id),
            trigger_at=trigger_at_utc.isoformat(),
            user_timezone=user_timezone,
        )

        return reminder

    async def list_pending_for_user(self, user_id: UUID) -> list[Reminder]:
        """List pending reminders for a user."""
        return await self.repository.get_pending_for_user(user_id)

    async def list_all_for_user(
        self,
        user_id: UUID,
        include_cancelled: bool = False,
    ) -> list[Reminder]:
        """List all reminders for a user."""
        return await self.repository.get_all_for_user(
            user_id,
            include_cancelled=include_cancelled,
        )

    async def cancel_reminder(self, reminder_id: UUID, user_id: UUID) -> Reminder:
        """
        Cancel a pending reminder.

        Args:
            reminder_id: ID of the reminder to cancel
            user_id: ID of the user (for ownership check)

        Raises:
            ResourceNotFoundError: If reminder doesn't exist
            ResourceConflictError: If reminder is not in pending state

        Returns:
            Cancelled reminder instance
        """
        reminder = await self.get_by_id(reminder_id, user_id)

        if reminder.status != ReminderStatus.PENDING.value:
            raise ResourceConflictError(
                f"Reminder {reminder_id} cannot be cancelled (status: {reminder.status})"
            )

        reminder = await self.repository.cancel_reminder(reminder)

        logger.info(
            "reminder_cancelled",
            reminder_id=str(reminder_id),
            user_id=str(user_id),
        )

        return reminder

    async def resolve_reminder(
        self,
        user_id: UUID,
        identifier: str,
    ) -> Reminder:
        """Resolve a reminder identifier to a Reminder object without cancelling.

        Supports:
        - UUID string
        - "le prochain" / "the next one" → earliest pending reminder
        - Numeric index (1, 2, 3...) from list
        - Content substring match

        Args:
            user_id: User ID
            identifier: UUID, reference string, or numeric index

        Raises:
            ResourceNotFoundError: If no matching reminder found.

        Returns:
            Resolved Reminder instance (not cancelled).
        """
        # Try UUID first
        try:
            reminder_id = UUID(identifier)
            return await self.get_by_id(reminder_id, user_id)
        except ValueError:
            pass

        # Get pending reminders for user
        pending_reminders = await self.list_pending_for_user(user_id)

        if not pending_reminders:
            raise ResourceNotFoundError("reminder", "no pending reminders found")

        # Handle natural language references
        identifier_lower = identifier.lower().strip()

        if identifier_lower in ("le prochain", "the next", "next", "1", "premier", "first"):
            return pending_reminders[0]

        if identifier_lower in ("le dernier", "the last", "last"):
            return pending_reminders[-1]

        # Try numeric index
        try:
            idx = int(identifier) - 1  # 1-indexed
            if 0 <= idx < len(pending_reminders):
                return pending_reminders[idx]
        except ValueError:
            pass

        # Try content match
        for reminder in pending_reminders:
            if identifier_lower in reminder.content.lower():
                return reminder

        raise ResourceNotFoundError(
            "reminder",
            f"no reminder found matching '{identifier}'",
        )

    async def resolve_and_cancel(
        self,
        user_id: UUID,
        identifier: str,
    ) -> Reminder:
        """Resolve a reminder identifier and cancel it.

        Args:
            user_id: User ID
            identifier: UUID, reference string, or numeric index

        Returns:
            Cancelled reminder
        """
        reminder = await self.resolve_reminder(user_id, identifier)
        return await self.cancel_reminder(reminder.id, user_id)
