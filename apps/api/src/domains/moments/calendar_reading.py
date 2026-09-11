"""Reading a provider event, once, for the three things that read one.

The score, the detector and the in-meeting guard all have to answer the same
four questions about an event: when does it start, when does it end, is it an
all-day block, and who is on it. Written three times they had already started to
diverge — the detector and the score each carried their own ``_instant`` — and
the guard was about to import the score's PRIVATE helpers to get a fourth.

All three connectors normalize to the Google shape (Microsoft through its
normalizer, Apple by parsing PARTSTAT), so one reading serves them all.

Everything here is pure and forgiving: an unreadable field yields ``None`` or an
empty list rather than raising. A provider shape drift must cost one decision,
never a sweep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def event_instant(field: Mapping[str, Any] | None, user_tz: ZoneInfo) -> datetime | None:
    """Read one end of an event as an aware instant, or admit it cannot.

    Args:
        field: The provider's ``start``/``end`` dict.
        user_tz: Fallback zone for a naive local time.

    Returns:
        The instant, or None for an all-day field or an unreadable one.
    """
    if not isinstance(field, Mapping):
        return None
    raw = field.get("dateTime")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed
    zone_name = field.get("timeZone")
    try:
        return parsed.replace(tzinfo=ZoneInfo(zone_name) if zone_name else user_tz)
    except KeyError, ValueError:
        return parsed.replace(tzinfo=user_tz)


def is_all_day(event: Mapping[str, Any]) -> bool:
    """True when either end carries a bare date — the all-day convention."""
    for key in ("start", "end"):
        field = event.get(key)
        if isinstance(field, Mapping) and field.get("date") and not field.get("dateTime"):
            return True
    return False


def attendees_of(event: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """The attendee entries, skipping anything that is not one."""
    raw = event.get("attendees")
    return [entry for entry in raw if isinstance(entry, Mapping)] if isinstance(raw, list) else []


def is_self(entry: Mapping[str, Any], folded_me: str | None) -> bool:
    """Whether this attendee is the account holder.

    ``self: True`` is Google's own marker and the most reliable signal; the
    address is the fallback, folded on both sides. With no known address nobody
    is « self », which only ever makes a rule more permissive — it never makes
    it wrong about a decline it could not read.

    Args:
        entry: One attendee (or an organizer, same shape).
        folded_me: The account holder's folded address, or None.

    Returns:
        True when the entry is the account holder.
    """
    from src.domains.shared.text_normalization import fold_email

    if entry.get("self") is True:
        return True
    email = entry.get("email")
    if folded_me is None or not isinstance(email, str):
        return False
    return fold_email(email) == folded_me


def is_declined_by_self(event: Mapping[str, Any], folded_me: str | None) -> bool:
    """Whether the account holder said they would not be there."""
    mine = [entry for entry in attendees_of(event) if is_self(entry, folded_me)]
    return any(str(entry.get("responseStatus") or "").lower() == "declined" for entry in mine)


def is_cancelled(event: Mapping[str, Any]) -> bool:
    """Whether the provider marked the event cancelled."""
    return str(event.get("status") or "").lower() == "cancelled"
