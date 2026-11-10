"""What a calendar event links to, read once for every surface that shows it.

The Tools' event detail and the home's agenda card both offer to join an event's
video call. The link comes from an invitation, which its sender wrote, so it is
handed to a page only as a web address with a host — never a script or a data URI.
Google keeps Meet's link in ``hangoutLink`` and a conference's doors in
``conferenceData.entryPoints``; the Graph normaliser writes a Teams join link into
both shapes (``microsoft_calendar_normalizer``), so one reading serves every provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from urllib.parse import urlsplit

#: The only links an event may hand the page: an invitation's sender wrote them.
WEB_SCHEMES: Final = frozenset({"https", "http"})

#: The event fields a provider must be asked for when a reader projects them.
CONFERENCE_FIELDS: Final = ("hangoutLink", "conferenceData")


def web_address(value: object) -> str | None:
    """``value`` when it is a web address with a host; never a script or a data URI.

    Args:
        value: A link as a provider answered it.

    Returns:
        The link, or None when it is not a web address.
    """
    if not isinstance(value, str) or not value:
        return None
    parts = urlsplit(value)
    return value if parts.scheme.lower() in WEB_SCHEMES and parts.netloc else None


def conference_url(raw: Mapping[str, Any]) -> str | None:
    """Meet's link, or the video entry point Graph's Teams link is normalised into.

    Args:
        raw: A provider event in the Google shape.

    Returns:
        The video call's web address, or None when the event holds none.
    """
    if found := web_address(raw.get("hangoutLink")):
        return found
    conference = raw.get("conferenceData")
    entries = conference.get("entryPoints") if isinstance(conference, Mapping) else None
    for entry in entries if isinstance(entries, list) else []:
        if (
            isinstance(entry, Mapping)
            and entry.get("entryPointType") == "video"
            and (found := web_address(entry.get("uri")))
        ):
            return found
    return None


__all__ = ["CONFERENCE_FIELDS", "WEB_SCHEMES", "conference_url", "web_address"]
