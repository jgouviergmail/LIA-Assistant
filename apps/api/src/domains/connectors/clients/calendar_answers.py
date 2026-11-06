"""Answering an invitation, on every calendar provider (ADR-369, lot 5).

The person answers for themselves alone. Google keeps the answer on the attendee it
marks ``self`` and tells the organiser when asked to; Graph has one act per answer;
CalDAV changes the person's own ``PARTSTAT`` and the server tells the organiser
(RFC 6638 §3.2.2.1). An event that names nobody the account answers to has nothing to
answer, and the answer is refused rather than written on somebody else's line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

EventAnswer = Literal["accepted", "declined", "tentative"]

#: What CalDAV calls each answer.
PARTSTATS: Final[dict[EventAnswer, str]] = {
    "accepted": "ACCEPTED",
    "declined": "DECLINED",
    "tentative": "TENTATIVE",
}
#: The act Graph has for each answer.
GRAPH_ACTS: Final[dict[EventAnswer, str]] = {
    "accepted": "accept",
    "declined": "decline",
    "tentative": "tentativelyAccept",
}


class NotInvitedError(Exception):
    """The event does not name the person among those invited."""


def own_answer(event: Mapping[str, Any]) -> str | None:
    """What the person answered, in Google's words; None when nothing invites them.

    Graph says it, the others mark the person's attendee ``self``. An organiser has no
    invitation, though Google lists them among the attendees like anyone.

    Args:
        event: The event, as the normalisers give it.

    Returns:
        The answer, or None for an event with nothing for this person to answer.
    """
    if (event.get("organizer") or {}).get("self"):
        return None
    if event.get("myResponse") is not None:
        return str(event["myResponse"])
    mine = next((item for item in event.get("attendees") or [] if item.get("self")), None)
    return None if mine is None else str(mine.get("responseStatus"))


__all__ = ["GRAPH_ACTS", "PARTSTATS", "EventAnswer", "NotInvitedError", "own_answer"]
