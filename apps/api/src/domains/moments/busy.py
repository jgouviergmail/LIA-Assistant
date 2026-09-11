"""Is this person in a meeting right now — the question the cooldowns never ask.

Nothing stopped the heartbeat interrupting someone mid-meeting. The nearest
guard is the activity cooldown, and it answers a different question: « did they
just type? ». Someone in a meeting precisely does not type, so that guard reads
their silence as availability — it is the moment it believes them MOST
available.

The exclusions mirror ``importance.score_event``, for the same reasons: a solo
slot is a block in a calendar rather than a room they are in, an all-day event
is not an occupation, and a meeting they declined is not one they are at.

Pure, and it never raises: an unreadable event is simply not a meeting. Not
knowing is not a reason to stay silent, and certainly not a reason to take a
tick down.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.domains.moments.calendar_reading import (
    attendees_of,
    event_instant,
    is_all_day,
    is_cancelled,
    is_declined_by_self,
    is_self,
)
from src.domains.shared.text_normalization import fold_email


def _is_a_meeting_they_are_at(
    event: Mapping[str, Any],
    *,
    folded_me: str | None,
) -> bool:
    """Whether this event is a real meeting this person is attending."""
    if is_cancelled(event) or is_all_day(event):
        return False
    if not [entry for entry in attendees_of(event) if not is_self(entry, folded_me)]:
        return False
    return not is_declined_by_self(event, folded_me)


def is_in_meeting(
    events: Sequence[Any],
    *,
    now: datetime,
    user_tz: ZoneInfo,
    user_email: str | None,
) -> bool:
    """Whether a meeting this person attends is in progress at ``now``.

    Args:
        events: Provider events, Google-shaped. Anything unreadable in the list
            is stepped over rather than raising.
        now: The instant to judge.
        user_tz: Fallback zone for a naive local time.
        user_email: The account holder's address, or None.

    Returns:
        True when at least one qualifying meeting has started and not ended.
    """
    folded_me = fold_email(user_email) if user_email else None
    for event in events:
        if not isinstance(event, Mapping):
            continue
        if not _is_a_meeting_they_are_at(event, folded_me=folded_me):
            continue
        start = event_instant(event.get("start"), user_tz)
        end = event_instant(event.get("end"), user_tz)
        if start is None or end is None:
            continue
        if start <= now < end:
            return True
    return False


def next_event_start(
    events: Sequence[Any],
    *,
    now: datetime,
    user_tz: ZoneInfo,
    user_email: str | None,
) -> datetime | None:
    """The earliest start, after ``now``, of an event this person still has.

    The second question the guard's calendar read answers (2026-09-11): the
    learned-rhythm tick scoring must not defer a tick toward an evening
    window while an appointment starts in an hour — the departure advice and
    the meeting reminder are what the tick exists for. Unlike
    :func:`is_in_meeting`, a SOLO appointment counts: the dentist has no
    attendees and is exactly what a departure advice serves. Cancelled,
    all-day and declined events do not.

    Args:
        events: Provider events, Google-shaped; unreadable entries are skipped.
        now: The instant to judge from.
        user_tz: Fallback zone for a naive local time.
        user_email: The account holder's address, or None.

    Returns:
        The earliest future start, or None when nothing is ahead.
    """
    folded_me = fold_email(user_email) if user_email else None
    earliest: datetime | None = None
    for event in events:
        if not isinstance(event, Mapping):
            continue
        if is_cancelled(event) or is_all_day(event) or is_declined_by_self(event, folded_me):
            continue
        start = event_instant(event.get("start"), user_tz)
        if start is None or start <= now:
            continue
        if earliest is None or start < earliest:
            earliest = start
    return earliest
