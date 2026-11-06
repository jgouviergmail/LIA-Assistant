"""What a contact and the person exchanged (ADR-369, lot 14).

The latest mail each way and the latest meetings each organised, read on the person's own mailbox
and calendar by ADDRESS. ``relations`` holds the searches each provider can answer and what an
event says of its people; its own lens goes on to qualify what it selected, a step this screen
never takes: nothing here reaches a model or a register (D5).

A calendar answers a window oldest first, so a long read would hand back the oldest meetings and
cut the latest: the window walks back from now and stops once both lists are full. How far it
looked is stated. Each source says why it has nothing: « I could not look » is never « nothing ».
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_CONTACT_HISTORY_ITEMS,
    WORKBENCH_CONTACT_HISTORY_SPAN_DAYS,
    WORKBENCH_CONTACT_HISTORY_SPANS,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.protocols import CalendarClientProtocol, EmailClientProtocol
from src.domains.connectors.preferences.owner_defaults import (
    CALENDAR,
    resolve_owner_container_id,
)
from src.domains.relations.providers.emails import (
    NO_SUBJECT,
    exchange_queries,
    to_exchanged_email,
)
from src.domains.relations.providers.events import attends, event_instant, organizes
from src.domains.relations.providers.schemas import ExchangedEmail
from src.domains.shared.text_normalization import fold_email
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_CONNECTED, refusal_code_of
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.contacts import (
    ContactHistory,
    ContactHistoryQuery,
    HistoryMail,
    HistoryMeeting,
    HistorySource,
)

_MAIL = WorkbenchTool.MAIL
_CALENDAR = WorkbenchTool.CALENDAR
_ITEMS: Final = WORKBENCH_CONTACT_HISTORY_ITEMS
_SPAN: Final = timedelta(days=WORKBENCH_CONTACT_HISTORY_SPAN_DAYS)
_RECEIVED: Final = "received"
_UNDATED: Final = datetime.min.replace(tzinfo=UTC)

Standing = Literal["by_them", "by_you", "shared"]


@dataclass(slots=True)
class _Mail:
    received: list[HistoryMail] = field(default_factory=list)
    sent: list[HistoryMail] = field(default_factory=list)


@dataclass(slots=True)
class _Meetings:
    by_them: list[HistoryMeeting] = field(default_factory=list)
    by_you: list[HistoryMeeting] = field(default_factory=list)
    shared: list[HistoryMeeting] = field(default_factory=list)
    cut: bool = False
    #: A meeting across two windows is answered by both.
    seen: set[str] = field(default_factory=set)

    def full(self) -> bool:
        return len(self.by_them) >= _ITEMS and len(self.by_you) >= _ITEMS


async def contact_history(
    user_id: UUID, zone: ZoneInfo, query: ContactHistoryQuery, now: datetime
) -> ContactHistory:
    """The latest exchanges with a contact.

    Args:
        user_id: The account.
        zone: The person's, which a meeting's day is read on.
        query: The contact's addresses.
        now: What « latest » is measured from.

    Returns:
        What each source found, each saying why it has nothing.
    """
    addresses = list(dict.fromkeys(str(address) for address in query.address))
    (mail, mail_source), (meetings, calendar_source) = await asyncio.gather(
        _sourced(_mail_with(user_id, addresses), _Mail()),
        _sourced(_meetings_with(user_id, zone, addresses, now), _Meetings()),
    )
    return ContactHistory(
        mail=mail_source,
        received=mail.received,
        sent=mail.sent,
        calendar=calendar_source,
        organized_by_them=_latest(meetings.by_them),
        organized_by_you=_latest(meetings.by_you),
        shared=_latest(meetings.shared),
        meetings_window_days=WORKBENCH_CONTACT_HISTORY_SPAN_DAYS * WORKBENCH_CONTACT_HISTORY_SPANS,
        meetings_cut=meetings.cut,
    )


def _latest(meetings: list[HistoryMeeting]) -> list[HistoryMeeting]:
    """The latest first: Graph answers a window in no order it promises."""
    return sorted(meetings, key=lambda row: row.at or _UNDATED, reverse=True)[:_ITEMS]


async def _sourced[T](reading: Awaitable[T], nothing: T) -> tuple[T, HistorySource]:
    """What a source read, or why it could not: one failing leaves the other standing."""
    try:
        return await reading, "used"
    except BaseAPIException as refusal:
        missing = refusal_code_of(refusal) == NOT_CONNECTED
        return nothing, "disabled" if missing else "unavailable"


async def _mail_with(user_id: UUID, addresses: list[str]) -> _Mail:
    async with open_tool_client(_MAIL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_MAIL, "history", act=False):
            found: dict[str, ExchangedEmail] = {}
            for address in addresses:
                for direction, search in exchange_queries(address):
                    page = await client.search_emails(
                        search, max_results=_ITEMS, use_cache=False, headers_only=True
                    )
                    for message in page.get("messages") or []:
                        email = to_exchanged_email(message, direction)
                        if email is not None:
                            found.setdefault(email.id, email)
    latest = sorted(found.values(), key=lambda row: row.occurred_at or _UNDATED, reverse=True)
    return _Mail(
        received=[_mail_row(row) for row in latest if row.direction == _RECEIVED][:_ITEMS],
        sent=[_mail_row(row) for row in latest if row.direction != _RECEIVED][:_ITEMS],
    )


def _mail_row(email: ExchangedEmail) -> HistoryMail:
    subject = "" if email.subject == NO_SUBJECT else email.subject
    return HistoryMail(id=email.id, subject=subject, at=email.occurred_at)


async def _meetings_with(
    user_id: UUID, zone: ZoneInfo, addresses: list[str], now: datetime
) -> _Meetings:
    folded = {fold_email(address) for address in addresses}
    meetings = _Meetings()
    async with open_tool_client(_CALENDAR, user_id, container=CALENDAR) as opened:
        client: CalendarClientProtocol = opened.client
        async with provider_call(_CALENDAR, "history", act=False):
            calendar_id = await resolve_owner_container_id(
                client=client, name=opened.preferred_name, owner_id=user_id, container=CALENDAR
            )
            for index in range(WORKBENCH_CONTACT_HISTORY_SPANS):
                end = now - _SPAN * index
                window = await client.list_events_window(
                    calendar_id,
                    (end - _SPAN).isoformat(),
                    end.isoformat(),
                    bound=settings.workbench_calendar_window_max_events,
                )
                meetings.cut = meetings.cut or bool(window.get("truncated"))
                for event in window.get("events") or []:
                    _place(meetings, event, folded, calendar_id, zone)
                if meetings.full():
                    break
    return meetings


def _place(
    meetings: _Meetings,
    event: Mapping[str, Any],
    folded: set[str],
    calendar_id: str,
    zone: ZoneInfo,
) -> None:
    standing = _standing(event, folded)
    if standing is None:
        return
    row = _meeting_row(event, calendar_id, zone)
    if row is None or row.id in meetings.seen:
        return
    meetings.seen.add(row.id)
    {"by_them": meetings.by_them, "by_you": meetings.by_you, "shared": meetings.shared}[
        standing
    ].append(row)


def _standing(event: Mapping[str, Any], folded: set[str]) -> Standing | None:
    """Where a meeting stands between the two; another's meeting answers neither list."""
    if event.get("status") == "cancelled":
        return None
    raw = dict(event)
    if organizes(raw, folded):
        return "by_them"
    if not attends(raw, folded):
        return None
    organizer = event.get("organizer") or {}
    if organizer.get("self") is True:
        return "by_you"
    return None if organizer.get("email") else "shared"


def _meeting_row(
    event: Mapping[str, Any], calendar_id: str, zone: ZoneInfo
) -> HistoryMeeting | None:
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        return None
    raw = dict(event)
    start = event_instant(raw, "start")
    day_of_its_own = (event.get("start") or {}).get("date")
    all_day = isinstance(day_of_its_own, str)
    day = (
        day_of_its_own
        if all_day
        else (start.astimezone(zone).date().isoformat() if start else None)
    )
    return HistoryMeeting(
        id=event_id,
        title=str(event.get("summary") or "").strip(),
        at=start,
        day=day,
        all_day=all_day,
        calendar_id=calendar_id,
    )


__all__ = ["contact_history"]
