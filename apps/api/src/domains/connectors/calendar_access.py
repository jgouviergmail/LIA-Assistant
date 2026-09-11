"""One way to open the person's active calendar, for every surface that reads it.

Resolving the active provider, fetching the right shape of credentials, looking
up its client class, resolving the owner's default calendar and closing the
transport is eight lines that were written twice — in
``ContextAggregator._fetch_calendar`` and in ``briefing.fetchers.fetch_agenda``
— and that the moment detector was about to write a third time.

The two copies had already drifted, in the way this repository keeps measuring:
the heartbeat closes its client in a ``finally`` and names the reason (« C8 leak
class, same doctrine as briefing/fetchers »), while ``fetch_agenda`` — the very
module that comment points at — never closed its calendar client at all, though
its three sibling fetchers in the same file do. One implementation cannot drift
from itself.

**Every refusal is NAMED**, and the caller decides what it means: the briefing
turns « no connector » into « connect a calendar » and « no credentials » into
« your connection expired » — two different things to tell someone — while the
heartbeat returns quietly and the detector files nothing. Three legitimate
readings of one fact, so the fact, and its reason, is what this yields.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.service import ConnectorService


class CalendarUnavailable(str, Enum):
    """Why the calendar could not be opened.

    Named rather than collapsed to None: « you have not connected a calendar »
    and « your connection expired, sign in again » are different sentences to
    put in front of someone, and the briefing says both.
    """

    NO_CONNECTOR = "no_connector"
    NO_CREDENTIALS = "no_credentials"
    NO_CLIENT = "no_client"


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
    db: AsyncSession,
    user_id: UUID,
) -> AsyncIterator[CalendarAccess | CalendarUnavailable]:
    """Open the account's active calendar, and always close it again.

    Args:
        db: Session the connector lookups run on. The caller owns it.
        user_id: Whose calendar.

    Yields:
        The open access, or the named reason it could not be opened.
    """
    connector_service = ConnectorService(db)
    resolved_type = await resolve_active_connector(user_id, "calendar", connector_service)
    if resolved_type is None:
        yield CalendarUnavailable.NO_CONNECTOR
        return

    credentials: Any = (
        await connector_service.get_apple_credentials(user_id, resolved_type)
        if resolved_type.is_apple
        else await connector_service.get_connector_credentials(user_id, resolved_type)
    )
    if not credentials:
        yield CalendarUnavailable.NO_CREDENTIALS
        return

    client_class = ClientRegistry.get_client_class(resolved_type)
    if client_class is None:
        yield CalendarUnavailable.NO_CLIENT
        return

    client = client_class(user_id, credentials, connector_service)
    try:
        calendar_id: str = await resolve_owner_calendar_id(
            db=db, client=client, owner_id=user_id, connector_type=resolved_type
        )
        yield CalendarAccess(
            client=client,
            calendar_id=calendar_id,
            connector_type=resolved_type,
        )
    finally:
        # Deterministic close on every path, including the one where the
        # caller's body raised: this is the leak the extraction removes.
        await client.close()
