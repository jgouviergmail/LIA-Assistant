"""
Reminder service for business logic.

Pattern: Follows PersonalityService structure.

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.recurrence import (
    DailyTimes,
    RecurrenceSpec,
    TimeOfDay,
    next_occurrence,
    rearm_after,
)
from src.core.time_utils import now_utc
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.repository import ReminderRepository
from src.domains.reminders.schemas import ReminderCreate, ReminderUpdate

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


def once_at(instant_utc: datetime, user_timezone: str) -> RecurrenceSpec:
    """The recurrence of a reminder that happens exactly once.

    The same rule the migration applied to every existing row: read the
    instant in the reader's own zone, and store that wall clock. Seconds are
    dropped — a `TimeOfDay` has none — which costs nothing because
    ``trigger_at`` stays the armed instant and this spec only ever answers
    "what comes after", which for a single occurrence is nothing.

    Args:
        instant_utc: The instant the reminder is armed at (UTC).
        user_timezone: The reader's IANA zone.

    Returns:
        A `once` recurrence naming that local wall clock.
    """
    local = instant_utc.astimezone(ZoneInfo(user_timezone))
    return RecurrenceSpec(
        freq="once",
        anchor_date=local.date(),
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=local.hour, minute=local.minute),)),
    )


def next_arming(reminder: Reminder, *, now: datetime | None = None) -> datetime | None:
    """What to arm after this reminder's current occurrence — or nothing.

    THE rule of the domain, in one place. ``None`` means the reminder has no
    future and the caller deletes it; anything else is the instant to arm.

    A single occurrence answers ``None`` the first time, which is exactly the
    historical post-it behaviour — so nothing anywhere asks "is this reminder
    recurring". A daily one answers tomorrow. A bounded series answers ``None``
    after its last instant, and the row goes the same way as a post-it: a
    reminder with no future does not exist (owner decision, 2026-09-06).

    Args:
        reminder: The row that has just been served.
        now: Current instant (UTC); defaults to now.

    Returns:
        The next instant to arm, or ``None`` when nothing follows.
    """
    return rearm_after(
        reminder.recurrence_spec,
        reminder.user_timezone,
        due_at=reminder.trigger_at,
        now=now,
    )


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
        # ONE authority for the armed instant. When a recurrence is given, the
        # instant is DERIVED from it: a caller cannot hand in a schedule and a
        # contradicting time and have the row announce one while ringing at the
        # other. The schema refuses both together; this decides which one is
        # read when only one arrives.
        if data.recurrence is not None:
            derived = next_occurrence(data.recurrence, user_timezone, after=now_utc())
            if derived is None:
                raise ValueError("this recurrence has no future occurrence")
            trigger_at_utc = derived
        else:
            assert data.trigger_at is not None  # guaranteed by the schema
            trigger_at_utc = convert_to_utc(data.trigger_at, user_timezone)

        # Validate trigger time is in the future
        # Named `now`, not `now_utc`: a local of that name SHADOWS the imported
        # helper for the whole function, so the line above would have raised
        # `UnboundLocalError` at runtime. Ruff F823 caught it; the shadow was
        # harmless only while nothing else in here called the function.
        now = datetime.now(UTC)
        if trigger_at_utc <= now:
            # Allow a small grace period (30 seconds) for "in 1 minute"
            logger.warning(
                "reminder_trigger_in_past",
                trigger_at=trigger_at_utc.isoformat(),
                now=now.isoformat(),
            )

        recurrence = data.recurrence or once_at(trigger_at_utc, user_timezone)

        reminder = await self.repository.create(
            {
                "user_id": user_id,
                "content": data.content,
                "original_message": data.original_message,
                "trigger_at": trigger_at_utc,
                "user_timezone": user_timezone,
                "recurrence": recurrence.model_dump(mode="json"),
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

    async def recalculate_all_for_user(self, user_id: UUID, new_timezone: str) -> int:
        """Move every pending reminder to the reader's new zone.

        **A spec is a wall clock, and a wall clock follows the person** (owner
        decision, 2026-09-06). Someone who moves to Tokyo means 08:00 where
        they now live, and that is true of a single occurrence as much as of a
        daily one: one rule, no exception to remember.

        This CHANGES the historical behaviour, where a reminder's instant was
        frozen at creation. It is the price of having one rule instead of two,
        and it matches what the routines already do.

        A reminder that is DUE but not yet collected — the scheduler runs on a
        tick, so there is a window — has nothing ahead of it and answers
        ``None``. Such a row is left entirely alone, zone included: it is about
        to fire in the zone its instant was computed in, and stamping the new
        one on it would leave a row nobody can explain.

        Args:
            user_id: Owner of the reminders.
            new_timezone: The reader's new IANA zone.

        Returns:
            Number of reminders moved.
        """
        reminders = await self.repository.get_all_pending_for_user(user_id)
        moved = 0
        for reminder in reminders:
            spec = reminder.recurrence_spec
            # Strictly after NOW, read in the NEW zone: an occurrence still
            # ahead of the reader keeps its wall clock and simply lands on a
            # different instant, while one already behind them is not revived.
            arrival = next_occurrence(spec, new_timezone, after=datetime.now(UTC))
            if arrival is None:
                # Due already; it fires within the tick, in its own zone.
                continue
            reminder.user_timezone = new_timezone
            reminder.trigger_at = arrival
            moved += 1
        if reminders:
            await self.db.flush()
        return moved

    async def update_reminder(
        self,
        reminder_id: UUID,
        user_id: UUID,
        data: ReminderUpdate,
        user_timezone: str,
    ) -> Reminder:
        """Change what a reminder says or when it fires.

        A changed recurrence RE-ARMS the reminder from now, exactly as a
        changed routine does: the stored instant belongs to the old schedule
        and keeping it would fire once more on a rule the reader has replaced.

        Args:
            reminder_id: The reminder to change.
            user_id: The caller, checked against the row's owner.
            data: The fields to change; absent ones are left alone.
            user_timezone: The reader's zone, for a supplied local instant.

        Returns:
            The updated reminder.

        Raises:
            ResourceNotFoundError: Unknown id, or one owned by someone else.
            ResourceConflictError: The reminder is already being processed.
            ValueError: The new recurrence arms nothing (a date now past).
        """
        reminder = await self.get_by_id(reminder_id, user_id)
        if reminder.status != ReminderStatus.PENDING.value:
            raise ResourceConflictError(
                resource_type="reminder",
                reason="reminder_not_pending",
            )

        if data.content is not None:
            reminder.content = data.content

        if data.recurrence is not None:
            arrival = next_occurrence(data.recurrence, user_timezone, after=now_utc())
            if arrival is None:
                raise ValueError("this recurrence has no future occurrence")
            reminder.recurrence = data.recurrence.model_dump(mode="json")
            reminder.trigger_at = arrival
            reminder.user_timezone = user_timezone
        elif data.trigger_at is not None:
            # Moving a SINGLE occurrence: the derived `once` spec follows, or
            # the row would describe one time and fire at another.
            #
            # On a REPEATING reminder the same payload has no honest meaning —
            # the next re-arm reads the rule and throws the manual instant
            # away, so it would look like a change that silently undoes itself
            # (a snooze is a different feature, and would need to say so).
            if reminder.recurrence_spec.freq != "once":
                raise ValueError(
                    "a repeating reminder is moved by changing its recurrence, "
                    "not by setting a single instant"
                )
            moved = convert_to_utc(data.trigger_at, user_timezone)
            reminder.trigger_at = moved
            reminder.user_timezone = user_timezone
            reminder.recurrence = once_at(moved, user_timezone).model_dump(mode="json")

        await self.db.flush()
        logger.info(
            "reminder_updated",
            reminder_id=str(reminder.id),
            user_id=str(user_id),
            trigger_at=reminder.trigger_at.isoformat(),
            schedule_changed=data.recurrence is not None,
        )
        return reminder

    async def list_pending_for_user(self, user_id: UUID) -> list[Reminder]:
        """List pending reminders for a user."""
        return await self.repository.get_pending_for_user(user_id)

    async def list_pending_page(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Reminder], int]:
        """One page of the reminders still waiting, and the exact total.

        Both halves come from the same session and the same instant, so a
        reminder firing between two reads cannot leave a total the page
        contradicts.

        Read-only by design: a reminder is a temporary post-it, deleted once
        notified. This lists what is still COMING — it is not, and cannot
        become, a history of what was sent.

        Args:
            user_id: Owner — scopes both reads.
            limit: Page size.
            offset: Page offset.

        Returns:
            Tuple of (page, exact total).
        """
        reminders = await self.repository.get_pending_for_user(user_id, limit=limit, offset=offset)
        total = await self.repository.count_pending_for_user(user_id)
        return reminders, total

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
        with suppress(ValueError):
            reminder_id = UUID(identifier)
            return await self.get_by_id(reminder_id, user_id)

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
        with suppress(ValueError):
            idx = int(identifier) - 1  # 1-indexed
            if 0 <= idx < len(pending_reminders):
                return pending_reminders[idx]

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
