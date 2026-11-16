"""Postponing a fired reminder, or stopping it (ADR-268 amendment 2026-11-16).

ADR-268 first refused a snooze because a press could not say WHICH occurrence
it meant: a one-shot reminder is deleted the instant it fires, and a series has
already moved to its next instant. The answer is a record of the occurrence
itself (``ReminderFiring``), written before the notification leaves; every
press names that record, never the reminder:

- :meth:`ReminderFiringService.record` — the scheduler's write, before delivery;
- :meth:`ReminderFiringService.snooze` — a one-shot copy at the chosen instant
  AND the occurrence marked postponed, in ONE transaction under the
  occurrence's row lock: two presses from two devices postpone it once;
- :meth:`ReminderFiringService.stop` — the series it came from is deleted;
- :meth:`ReminderFiringService.state` — what the chat bubble offers;
- :meth:`ReminderFiringService.purge_expired` — kept for the window only.

A press is the person's own act: nothing here writes a register row (owner
decision 2026-10-30) or calls a model. The copy then rings as any reminder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import REMINDER_FIRINGS_PURGE_BATCH
from src.core.exceptions import ResourceNotFoundError
from src.domains.reminders.firing_repository import ReminderFiringRepository
from src.domains.reminders.firings import (
    FiringOffer,
    FiringSurface,
    SnoozeChoice,
    SnoozeDelays,
    SnoozeOutcome,
    StopOutcome,
    collides_with,
    snooze_instant,
)
from src.domains.reminders.models import Reminder, ReminderFiring, ReminderStatus
from src.domains.reminders.repository import ReminderRepository
from src.domains.reminders.service import next_arming, once_at
from src.infrastructure.observability.metrics_reminders import reminder_firing_actions_total

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SnoozeResult:
    """What a snooze press did.

    Attributes:
        outcome: The verdict.
        snoozed_until: The instant the reminder comes back (snoozed, or already).
        next_occurrence_at: The series' next occurrence a refused press met.
    """

    outcome: SnoozeOutcome
    snoozed_until: datetime | None = None
    next_occurrence_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class FiringState:
    """What the chat bubble of a fired reminder offers.

    Attributes:
        firing_id: The occurrence.
        fired_at: When it rang.
        snoozable_until: Past this instant nothing can be postponed.
        snoozed_until: Where a press already put it, if one did.
        stoppable: Whether the reminder has a future a press could stop.
        delays: The deployment's « later ».
    """

    firing_id: UUID
    fired_at: datetime
    snoozable_until: datetime
    snoozed_until: datetime | None
    stoppable: bool
    delays: SnoozeDelays


def snooze_window() -> timedelta:
    """How long after it rang an occurrence can still be postponed."""
    return timedelta(hours=settings.reminder_snooze_window_hours)


def upcoming_occurrence(reminder: Reminder | None, *, now: datetime) -> datetime | None:
    """The next instant a REPEATING reminder will ring, or None.

    A pending series rings next at ``trigger_at``. One still being notified —
    its occurrence rang but is not settled yet — rings next where its
    settlement will re-arm it. A single occurrence has no future to protect.

    Args:
        reminder: The reminder an occurrence came from, if it still exists.
        now: The present.

    Returns:
        The next instant, or None when nothing comes back.
    """
    if reminder is None or reminder.recurrence_spec.freq == "once":
        return None
    if reminder.status == ReminderStatus.PENDING.value:
        return reminder.trigger_at
    if reminder.status == ReminderStatus.PROCESSING.value:
        return next_arming(reminder, now=now)
    return None


class ReminderFiringService:
    """The occurrences of reminders that rang, and what a press does to them."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ReminderFiringRepository(db)
        self.reminders = ReminderRepository(db)

    async def record(self, reminder: Reminder, *, fired_at: datetime) -> FiringOffer:
        """Record the occurrence about to be notified.

        Args:
            reminder: The claimed reminder, still holding the occurrence.
            fired_at: When it rang.

        Returns:
            What its notification offers: the occurrence, until when, and
            whether a future exists to stop.
        """
        firing = await self.repository.create(
            {
                "user_id": reminder.user_id,
                "reminder_id": reminder.id,
                "content": reminder.content,
                "original_message": reminder.original_message,
                "asked_at": reminder.first_asked_at or reminder.created_at,
                "fired_at": fired_at,
            }
        )
        return FiringOffer(
            firing_id=firing.id,
            snoozable_until=fired_at + snooze_window(),
            stoppable=next_arming(reminder, now=fired_at) is not None,
        )

    async def state(self, firing_id: UUID, user_id: UUID, *, now: datetime) -> FiringState:
        """What the chat bubble of an occurrence offers.

        Raises:
            ResourceNotFoundError: Unknown occurrence, purged, or another account's.
        """
        firing = await self.repository.get_owned(firing_id, user_id)
        if firing is None:
            raise ResourceNotFoundError("reminder_firing", str(firing_id))
        series = await self._series_of(firing)
        return FiringState(
            firing_id=firing.id,
            fired_at=firing.fired_at,
            snoozable_until=firing.fired_at + snooze_window(),
            snoozed_until=firing.snoozed_until,
            stoppable=upcoming_occurrence(series, now=now) is not None,
            delays=SnoozeDelays.from_settings(),
        )

    async def snooze(
        self,
        firing_id: UUID,
        user_id: UUID,
        choice: SnoozeChoice,
        *,
        zone: str,
        now: datetime,
        surface: FiringSurface,
    ) -> SnoozeResult:
        """Bring an occurrence back later, once.

        Under the occurrence's row lock: the copy and the mark are written in
        the caller's transaction, so a second press — another device, a double
        tap — reads the first one's verdict instead of creating a second copy.

        Args:
            firing_id: The occurrence the press names.
            user_id: The caller.
            choice: Which « later ».
            zone: The account's zone, which « tomorrow morning » is read in.
            now: The press.
            surface: Where the press came from (counted).

        Returns:
            The verdict, with the instants it rests on.

        Raises:
            ResourceNotFoundError: Unknown occurrence, purged, or another account's.
        """
        firing = await self.repository.lock_owned(firing_id, user_id)
        if firing is None:
            raise ResourceNotFoundError("reminder_firing", str(firing_id))
        result = await self._snooze_locked(firing, choice, zone=ZoneInfo(zone), now=now)
        reminder_firing_actions_total.labels(
            surface=surface.value, action="snooze", outcome=result.outcome.value
        ).inc()
        logger.info(
            "reminder_firing_snoozed",
            firing_id=str(firing_id),
            user_id=str(user_id),
            choice=choice.value,
            surface=surface.value,
            outcome=result.outcome.value,
        )
        return result

    async def _snooze_locked(
        self, firing: ReminderFiring, choice: SnoozeChoice, *, zone: ZoneInfo, now: datetime
    ) -> SnoozeResult:
        if firing.snoozed_until is not None:
            return SnoozeResult(SnoozeOutcome.ALREADY_SNOOZED, snoozed_until=firing.snoozed_until)
        if now >= firing.fired_at + snooze_window():
            return SnoozeResult(SnoozeOutcome.EXPIRED)
        target = snooze_instant(choice, now=now, zone=zone, delays=SnoozeDelays.from_settings())
        upcoming = upcoming_occurrence(await self._series_of(firing), now=now)
        if collides_with(target, upcoming):
            return SnoozeResult(SnoozeOutcome.COLLIDES, next_occurrence_at=upcoming)
        await self.reminders.create(
            {
                "user_id": firing.user_id,
                "content": firing.content,
                "original_message": firing.original_message,
                "trigger_at": target,
                "user_timezone": zone.key,
                "recurrence": once_at(target, zone.key).model_dump(mode="json"),
                "status": ReminderStatus.PENDING.value,
                "first_asked_at": firing.asked_at,
            }
        )
        firing.snoozed_until = target
        await self.db.flush()
        return SnoozeResult(SnoozeOutcome.SNOOZED, snoozed_until=target)

    async def stop(
        self, firing_id: UUID, user_id: UUID, *, now: datetime, surface: FiringSurface
    ) -> StopOutcome:
        """Delete the series an occurrence came from: it will not ring again.

        A reminder still being notified is deleted too: its settlement finds
        the claim gone and leaves it alone (the rule an owner's deletion
        already follows).

        Args:
            firing_id: The occurrence the press names.
            user_id: The caller.
            now: The press.
            surface: Where the press came from (counted).

        Returns:
            Stopped, or already stopped (deleted meanwhile, or nothing to stop).

        Raises:
            ResourceNotFoundError: Unknown occurrence, purged, or another account's.
        """
        firing = await self.repository.get_owned(firing_id, user_id)
        if firing is None:
            raise ResourceNotFoundError("reminder_firing", str(firing_id))
        outcome = StopOutcome.ALREADY_STOPPED
        if firing.reminder_id is not None:
            series = await self.reminders.lock_owned(firing.reminder_id, user_id)
            if series is not None and upcoming_occurrence(series, now=now) is not None:
                await self.reminders.cancel_reminder(series)
                outcome = StopOutcome.STOPPED
        reminder_firing_actions_total.labels(
            surface=surface.value, action="stop", outcome=outcome.value
        ).inc()
        logger.info(
            "reminder_firing_stopped",
            firing_id=str(firing_id),
            user_id=str(user_id),
            surface=surface.value,
            outcome=outcome.value,
        )
        return outcome

    async def purge_expired(self, *, now: datetime) -> int:
        """Delete a batch of occurrences whose window has closed.

        Returns:
            The exact number deleted.
        """
        return await self.repository.purge_fired_before(
            now - snooze_window(), limit=REMINDER_FIRINGS_PURGE_BATCH
        )

    async def _series_of(self, firing: ReminderFiring) -> Reminder | None:
        """The reminder an occurrence came from, while it exists (owner-scoped)."""
        if firing.reminder_id is None:
            return None
        reminder = await self.reminders.get_by_id(firing.reminder_id)
        if reminder is None or reminder.user_id != firing.user_id:
            return None
        return reminder
