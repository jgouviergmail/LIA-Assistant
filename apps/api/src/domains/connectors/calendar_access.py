"""One way to open the person's active calendar, for every surface that reads it.

Resolving the active provider, fetching the right shape of credentials, looking
up its client class, resolving the owner's default calendar and closing the
transport was written twice — in ``ContextAggregator._fetch_calendar`` and in
``briefing.fetchers.fetch_agenda`` — and the moment detector was about to write
it a third time. The two copies had already drifted: the heartbeat closed its
client in a ``finally``, ``fetch_agenda`` never closed it at all. One
implementation cannot drift from itself.

Since ADR-304 it holds no database session either: it opens through
``connectors.active_client`` — every read in one short session of its own,
closed before the provider is called — and resolves the owner's configured
calendar on the network afterwards. It used to take the caller's session and
keep a transaction open for as long as the calendar answered.

**Every refusal is NAMED**, and the caller decides what it means: the briefing
turns « no connector » into « connect a calendar » and « no credentials » into
« your connection expired » — two different things to tell someone — while the
heartbeat returns quietly and the detector files nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.domains.connectors.active_client import (
    ActiveClient,
    ClientUnavailable,
    open_active_client,
)
from src.domains.connectors.preferences.owner_defaults import (
    CALENDAR,
    resolve_owner_container_id,
)

#: Why the calendar could not be opened — the door's own vocabulary, named
#: here for the calendar's readers (« connect a calendar » is not « your
#: connection expired »).
CalendarUnavailable = ClientUnavailable


@dataclass(frozen=True, slots=True)
class CalendarAccess:
    """An open calendar client and the calendar it should read.

    Attributes:
        client: The provider client, live for the length of the ``async with``.
        calendar_id: The owner's preferred default calendar, or ``primary``.
        connector_type: Which provider answered, for logging and for callers
            that branch on Apple.
    """

    client: Any
    calendar_id: str
    connector_type: Any


@asynccontextmanager
async def open_active_calendar(
    user_id: UUID,
) -> AsyncIterator[CalendarAccess | ClientUnavailable]:
    """Open the account's active calendar, and always close it again.

    Args:
        user_id: Whose calendar.

    Yields:
        The open access, or the named reason it could not be opened. No
        database session is open while the caller reads the calendar.
    """
    async with open_active_client("calendar", user_id, container=CALENDAR) as opened:
        if not isinstance(opened, ActiveClient):
            yield opened
            return
        calendar_id = await resolve_owner_container_id(
            client=opened.client,
            name=opened.preferred_name,
            owner_id=user_id,
            container=CALENDAR,
        )
        yield CalendarAccess(
            client=opened.client,
            calendar_id=calendar_id,
            connector_type=opened.connector_type,
        )
