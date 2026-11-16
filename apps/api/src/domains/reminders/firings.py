"""What a press on a fired reminder asks, and when it brings it back.

ADR-268 amendment 2026-11-16. Pure: no database, no clock of its own. The
service (``firing_service``) reads the instant a press lands on and the rule
that refuses one a series already covers; the surfaces read the vocabulary.

« Tomorrow morning » is a wall time: it is read on the account's wall through
:class:`~src.core.wall_time.WallTime` (ADR-380), never by adding hours to an
instant, which lands an hour off on the night the clocks change. The two other
choices are durations of life, added to the instant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import REMINDER_SNOOZE_NIGHT_END_HOUR
from src.core.wall_time import WallTime


class SnoozeChoice(StrEnum):
    """The three « later » a fired reminder offers."""

    SHORT = "short"
    LONG = "long"
    MORNING = "morning"


class SnoozeOutcome(StrEnum):
    """What a snooze press did."""

    SNOOZED = "snoozed"
    ALREADY_SNOOZED = "already_snoozed"
    EXPIRED = "expired"
    COLLIDES = "collides"


class StopOutcome(StrEnum):
    """What a « stop this reminder » press did."""

    STOPPED = "stopped"
    ALREADY_STOPPED = "already_stopped"


class FiringSurface(StrEnum):
    """Where a press on a fired reminder came from (the metric's label)."""

    CHAT = "chat"
    PUSH = "push"
    TELEGRAM = "telegram"


@dataclass(frozen=True, slots=True)
class SnoozeDelays:
    """The instance's « later », read once per press.

    Attributes:
        short_minutes: « In 10 min ».
        long_minutes: « In 1 h ».
        morning_hour: The hour « tomorrow morning » means on the account's wall.
    """

    short_minutes: int
    long_minutes: int
    morning_hour: int

    @classmethod
    def from_settings(cls) -> SnoozeDelays:
        """The delays the deployment configured."""
        return cls(
            short_minutes=settings.reminder_snooze_short_minutes,
            long_minutes=settings.reminder_snooze_long_minutes,
            morning_hour=settings.reminder_snooze_morning_hour,
        )


@dataclass(frozen=True, slots=True)
class FiringOffer:
    """What a notification needs to offer the postponement of its occurrence.

    Attributes:
        firing_id: The occurrence every press names.
        snoozable_until: Past this instant a press answers « expired ».
        stoppable: Whether the reminder has a future a press could stop.
    """

    firing_id: UUID
    snoozable_until: datetime
    stoppable: bool


def snooze_instant(
    choice: SnoozeChoice, *, now: datetime, zone: ZoneInfo, delays: SnoozeDelays
) -> datetime:
    """The instant a postponed reminder rings again.

    Args:
        choice: What the person pressed.
        now: The press (an aware instant).
        zone: The account's zone, which « tomorrow morning » is read in.
        delays: The deployment's three « later ».

    Returns:
        The instant, always after ``now``.
    """
    if choice is SnoozeChoice.SHORT:
        return now + timedelta(minutes=delays.short_minutes)
    if choice is SnoozeChoice.LONG:
        return now + timedelta(minutes=delays.long_minutes)
    return _next_morning(now, zone, delays.morning_hour)


def _next_morning(now: datetime, zone: ZoneInfo, hour: int) -> datetime:
    """The coming morning at ``hour`` on ``zone``'s wall.

    Before the end of the night it is the morning of the same day, as a person
    still up at 01:00 means it; a morning already behind the press (an hour
    configured before the night's end) is the next one.
    """
    wall = WallTime.seen_from(now, zone).local
    day = wall.date()
    if wall.hour >= REMINDER_SNOOZE_NIGHT_END_HOUR:
        day += timedelta(days=1)
    target = WallTime(datetime.combine(day, time(hour)), zone).instant()
    if target <= now:
        target = WallTime(datetime.combine(day + timedelta(days=1), time(hour)), zone).instant()
    return target


def collides_with(target: datetime, upcoming: datetime | None) -> bool:
    """Whether a postponement would ring at or after the series' next occurrence.

    The series reminds the person then anyway: a copy ringing later would say
    the same thing twice, so the press is refused with that instant.

    Args:
        target: Where the press would put the copy.
        upcoming: The series' next occurrence, None when nothing comes back.

    Returns:
        True when the press must be refused.
    """
    return upcoming is not None and target >= upcoming


__all__ = [
    "FiringOffer",
    "FiringSurface",
    "SnoozeChoice",
    "SnoozeDelays",
    "SnoozeOutcome",
    "StopOutcome",
    "collides_with",
    "snooze_instant",
]
