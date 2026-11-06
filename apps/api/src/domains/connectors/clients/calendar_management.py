"""Moving an event between calendars, and managing calendars (ADR-369, lot 5).

Google moves an event by name, its id kept. Graph has no such act and CalDAV none its
servers share: there an event is copied, then its original removed. A copy reaches the
attendees twice (a new invitation, a cancellation), breaks a series and, on Graph, loses
attachments: what would be reached or lost is refused before anything is sent.

The original removed last: an event is never lost, and one that could not be removed is
said to stand in both calendars rather than left to be found twice.
"""

from __future__ import annotations


class EventNotMovableError(Exception):
    """A copy would reach guests, break a series or lose attachments: nothing was sent."""


class EventLeftBehindError(Exception):
    """The event reached its new calendar and its original could not be removed."""


__all__ = ["EventLeftBehindError", "EventNotMovableError"]
