"""What makes a finished meeting worth a word — a table, not a model call.

No LLM decides whether to wake. Two reasons, and both are settled elsewhere in
this repository: ADR-261 already refused an LLM pre-filter on the ground that
spending a model call to decide whether to spend a model call IS the noise, and
the measurement behind it is public — a deterministic trigger beats a
single-forward LLM on accuracy AND runs orders of magnitude faster.

The rule has two halves, and they answer different questions:

- **necessary conditions** decide whether a debrief could ever make sense. A
  solo slot, a five-minute call, a whole day off, something declined, something
  cancelled: asking how any of those went is absurd, and no amount of points
  redeems it. One missing and nothing is counted.
- **points** decide which of the remaining events actually earn the
  interruption. The threshold is a published setting (ADR-184), so an operator
  makes LIA quieter or more forthcoming without a deploy.

Pure by construction: no I/O, no clock, no session. Whoever calls it resolves
the favourites and the linked commitments first, so the same event scores the
same way in a test and in the sweep.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from src.core.config import get_settings
from src.domains.moments.calendar_reading import (
    attendees_of,
    event_instant,
    is_all_day,
    is_cancelled,
    is_declined_by_self,
    is_self,
)
from src.domains.shared.text_normalization import fold_email, fold_name


class BlockedBy(str, Enum):
    """Why an event earns no moment at all.

    Bounded because it is logged and counted: « the feature is quiet because
    nothing qualified » and « the feature is quiet because every event is
    all-day » are different operational answers.
    """

    NO_OTHER_ATTENDEE = "no_other_attendee"
    TOO_SHORT = "too_short"
    ALL_DAY = "all_day"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    UNREADABLE = "unreadable"
    BELOW_THRESHOLD = "below_threshold"


class ScoreReason(str, Enum):
    """What earned a point. Lands in the payload and in the operator log."""

    HAS_OTHER_ATTENDEE = "has_other_attendee"
    SEVERAL_ATTENDEES = "several_attendees"
    HAS_LOCATION = "has_location"
    IS_ORGANIZER = "is_organizer"
    FAVORITE_ATTENDEE = "favorite_attendee"
    LINKED_COMMITMENT = "linked_commitment"


@dataclass(frozen=True, slots=True)
class EventScore:
    """The verdict on one finished event.

    Attributes:
        worthy: Whether this event earns a moment.
        score: Points counted. Zero when a necessary condition failed — nothing
            is counted in that case, so a caller cannot read a partial score as
            « nearly worthy ».
        reasons: What earned each point, in a STABLE order: two identical events
            must read identically from one pass to the next, and a set would not
            guarantee that.
        blocked_by: What refused it, or None when it is worthy.
    """

    worthy: bool
    score: int
    reasons: tuple[ScoreReason, ...]
    blocked_by: BlockedBy | None


#: The order points are counted in — and therefore the order they are reported
#: in. Declared rather than implied by the code's shape, so a refactor cannot
#: silently reorder what an operator reads.
_REASON_ORDER: tuple[ScoreReason, ...] = (
    ScoreReason.HAS_OTHER_ATTENDEE,
    ScoreReason.SEVERAL_ATTENDEES,
    ScoreReason.HAS_LOCATION,
    ScoreReason.IS_ORGANIZER,
    ScoreReason.FAVORITE_ATTENDEE,
    ScoreReason.LINKED_COMMITMENT,
)


def _blocked(reason: BlockedBy) -> EventScore:
    """A refusal counts nothing: a partial score would read as « nearly »."""
    return EventScore(worthy=False, score=0, reasons=(), blocked_by=reason)


def _has_place(event: Mapping[str, Any]) -> bool:
    """A room or a video link — a remote meeting is still held somewhere."""
    if str(event.get("location") or "").strip():
        return True
    if str(event.get("hangoutLink") or "").strip():
        return True
    conference = event.get("conferenceData")
    return isinstance(conference, Mapping) and bool(conference)


def _person_keys(entry: Mapping[str, Any]) -> set[str]:
    """Every folded spelling this attendee answers to.

    The display name is what ``relation_favorites`` and the commitments store,
    so it is the join key; the local part of the address is a fallback for a
    guest the provider gave no name for.
    """
    keys: set[str] = set()
    name = entry.get("displayName")
    if isinstance(name, str) and name.strip():
        keys.add(fold_name(name))
    email = entry.get("email")
    if isinstance(email, str) and "@" in email:
        keys.add(fold_name(email.split("@", 1)[0].replace(".", " ")))
    return keys


def _screen_shape(
    event: Mapping[str, Any],
    *,
    user_tz: ZoneInfo,
    min_duration_minutes: int,
) -> BlockedBy | None:
    """What the event ITSELF disqualifies on: cancelled, all-day, too short.

    Args:
        event: The provider event.
        user_tz: Fallback zone for a naive local time.
        min_duration_minutes: Shortest event that can earn a follow-up.

    Returns:
        The refusal, or None when the shape is fine.
    """
    if is_cancelled(event):
        return BlockedBy.CANCELLED
    if is_all_day(event):
        return BlockedBy.ALL_DAY
    start = event_instant(event.get("start"), user_tz)
    end = event_instant(event.get("end"), user_tz)
    if start is None or end is None:
        return BlockedBy.UNREADABLE
    if (end - start).total_seconds() / 60 < min_duration_minutes:
        return BlockedBy.TOO_SHORT
    return None


def _screen_people(
    event: Mapping[str, Any],
    *,
    folded_me: str | None,
) -> tuple[BlockedBy | None, list[Mapping[str, Any]]]:
    """Who was there, and whether that disqualifies the event.

    Args:
        event: The provider event.
        folded_me: The account holder's folded address, or None.

    Returns:
        The refusal (or None) and the attendees who are not the account holder.
    """
    attendees = attendees_of(event)
    others = [entry for entry in attendees if not is_self(entry, folded_me)]
    if not others:
        return BlockedBy.NO_OTHER_ATTENDEE, []
    # ONE reading of « did they say they would not be there », shared with the
    # revalidation: this used to carry its own copy of the same expression.
    if is_declined_by_self(event, folded_me):
        return BlockedBy.DECLINED, []
    return None, others


def _screen(
    event: Mapping[str, Any],
    *,
    user_tz: ZoneInfo,
    folded_me: str | None,
    min_duration_minutes: int,
) -> tuple[BlockedBy | None, list[Mapping[str, Any]]]:
    """Apply the necessary conditions, and hand back the other attendees.

    Split out of :func:`score_event` so the two halves of the rule read
    separately: what makes a debrief absurd, and what makes one worth having.

    Args:
        event: The provider event, Google-shaped.
        user_tz: Fallback zone for a naive local time.
        folded_me: The account holder's folded address, or None.
        min_duration_minutes: Shortest event that can earn a follow-up.

    Returns:
        The refusal (or None), and the attendees who are not the account
        holder — computed here so the caller need not walk them twice.
    """
    shape = _screen_shape(event, user_tz=user_tz, min_duration_minutes=min_duration_minutes)
    if shape is not None:
        return shape, []
    return _screen_people(event, folded_me=folded_me)


def _earned(
    event: Mapping[str, Any],
    others: list[Mapping[str, Any]],
    *,
    folded_me: str | None,
    favorite_keys: frozenset[str],
    linked_keys: frozenset[str],
) -> set[ScoreReason]:
    """Count what makes this particular meeting worth asking about.

    Args:
        event: The provider event.
        others: Attendees who are not the account holder.
        folded_me: The account holder's folded address, or None.
        favorite_keys: Folded names of the people they marked as favourites.
        linked_keys: Folded names cited by an open ticket or an open loop.

    Returns:
        The reasons earned, unordered — :func:`score_event` orders them.
    """
    earned: set[ScoreReason] = {ScoreReason.HAS_OTHER_ATTENDEE}
    if len(others) > 1:
        earned.add(ScoreReason.SEVERAL_ATTENDEES)
    if _has_place(event):
        earned.add(ScoreReason.HAS_LOCATION)
    organizer = event.get("organizer")
    if isinstance(organizer, Mapping) and is_self(organizer, folded_me):
        earned.add(ScoreReason.IS_ORGANIZER)

    if not (favorite_keys or linked_keys):
        return earned
    keys: set[str] = set()
    for entry in others:
        keys |= _person_keys(entry)
    if keys & favorite_keys:
        earned.add(ScoreReason.FAVORITE_ATTENDEE)
    if keys & linked_keys:
        earned.add(ScoreReason.LINKED_COMMITMENT)
    return earned


def score_event(
    event: Mapping[str, Any],
    *,
    user_email: str | None,
    favorite_keys: frozenset[str],
    linked_keys: frozenset[str],
    user_tz: ZoneInfo,
) -> EventScore:
    """Decide whether a finished event earns a debrief.

    Args:
        event: The provider event, normalized to the Google shape (all three
            connectors produce it — Microsoft through its normalizer, Apple by
            parsing PARTSTAT).
        user_email: The account holder's address, for telling them apart from
            their guests. None is tolerated (see :func:`_is_self`).
        favorite_keys: Folded names of the people they marked as favourites.
        linked_keys: Folded names cited by an open ticket or an open loop.
        user_tz: Fallback zone for a naive local time in the event.

    Returns:
        The verdict: worthy or refused, with what earned or refused it.
    """
    settings = get_settings()
    folded_me = fold_email(user_email) if user_email else None

    refusal, others = _screen(
        event,
        user_tz=user_tz,
        folded_me=folded_me,
        min_duration_minutes=settings.moments_event_min_duration_minutes,
    )
    if refusal is not None:
        return _blocked(refusal)

    earned = _earned(
        event,
        others,
        folded_me=folded_me,
        favorite_keys=favorite_keys,
        linked_keys=linked_keys,
    )
    reasons = tuple(reason for reason in _REASON_ORDER if reason in earned)
    score = len(reasons)
    if score < settings.moments_event_followup_min_score:
        return EventScore(
            worthy=False,
            score=score,
            reasons=reasons,
            blocked_by=BlockedBy.BELOW_THRESHOLD,
        )
    return EventScore(worthy=True, score=score, reasons=reasons, blocked_by=None)
