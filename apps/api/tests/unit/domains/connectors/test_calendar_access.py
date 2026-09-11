"""Opening the person's calendar, once, for the three surfaces that need it.

The same eight lines — resolve the active connector, fetch the right shape of
credentials, look up the client class, resolve the owner's default calendar,
close the transport — were written in ``ContextAggregator._fetch_calendar`` and
in ``briefing.fetchers.fetch_agenda``, and the moment detector was about to
write them a third time.

Extracting them is not tidying: the two copies had already DIVERGED. The
heartbeat closes its transport in a ``finally`` and says why (« C8 leak class,
same doctrine as briefing/fetchers ») — and ``fetch_agenda``, the very module
that comment points at, never closed its calendar client at all, while its three
sibling fetchers in the same file do. One implementation cannot drift from
itself, and this one closes by construction.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.calendar_access import (
    CalendarAccess,
    CalendarUnavailable,
    open_active_calendar,
)

pytestmark = pytest.mark.unit

_RESOLVE = "src.domains.connectors.calendar_access.resolve_active_connector"
_REGISTRY = "src.domains.connectors.calendar_access.ClientRegistry"
_OWNER_CALENDAR = "src.domains.connectors.calendar_access.resolve_owner_calendar_id"
_CONNECTOR_SERVICE = "src.domains.connectors.calendar_access.ConnectorService"


def _connector(*, is_apple: bool = False) -> Any:
    return SimpleNamespace(is_apple=is_apple, value="google_calendar")


def _service(credentials: Any = "creds") -> MagicMock:
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value=credentials)
    service.get_apple_credentials = AsyncMock(return_value=credentials)
    return service


def _client() -> MagicMock:
    client = MagicMock()
    client.close = AsyncMock()
    return client


class TestWhenTheCalendarOpens:
    async def test_it_yields_the_client_and_the_owner_default_calendar(self) -> None:
        client = _client()
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector())),
            patch(_REGISTRY) as registry,
            patch(_OWNER_CALENDAR, new=AsyncMock(return_value="work@group.calendar")),
        ):
            registry.get_client_class.return_value = MagicMock(return_value=client)

            async with open_active_calendar(MagicMock(), uuid4()) as access:
                assert isinstance(access, CalendarAccess)
                assert access.client is client
                assert access.calendar_id == "work@group.calendar"

    async def test_the_transport_is_closed_on_the_way_out(self) -> None:
        """The defect this extraction removes: fetch_agenda never closed it."""
        client = _client()
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector())),
            patch(_REGISTRY) as registry,
            patch(_OWNER_CALENDAR, new=AsyncMock(return_value="primary")),
        ):
            registry.get_client_class.return_value = MagicMock(return_value=client)

            async with open_active_calendar(MagicMock(), uuid4()):
                pass

        client.close.assert_awaited_once()

    async def test_the_transport_is_closed_even_when_the_body_raises(self) -> None:
        client = _client()
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector())),
            patch(_REGISTRY) as registry,
            patch(_OWNER_CALENDAR, new=AsyncMock(return_value="primary")),
        ):
            registry.get_client_class.return_value = MagicMock(return_value=client)

            with pytest.raises(ValueError):
                async with open_active_calendar(MagicMock(), uuid4()):
                    raise ValueError("the caller blew up")

        client.close.assert_awaited_once()

    async def test_apple_credentials_take_the_apple_door(self) -> None:
        """CalDAV credentials are resolved by a different method entirely."""
        service = _service()
        with (
            patch(_CONNECTOR_SERVICE, return_value=service),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector(is_apple=True))),
            patch(_REGISTRY) as registry,
            patch(_OWNER_CALENDAR, new=AsyncMock(return_value="primary")),
        ):
            registry.get_client_class.return_value = MagicMock(return_value=_client())

            async with open_active_calendar(MagicMock(), uuid4()):
                pass

        service.get_apple_credentials.assert_awaited_once()
        service.get_connector_credentials.assert_not_awaited()


class TestWhenThereIsNoCalendar:
    """Every refusal is NAMED: the caller decides what to say about it.

    « You have not connected a calendar » and « your connection expired » are
    different sentences to put in front of someone, and the briefing says both —
    so collapsing them to None here would flatten a real distinction.
    """

    async def test_no_active_connector(self) -> None:
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=None)),
        ):
            async with open_active_calendar(MagicMock(), uuid4()) as access:
                assert access is CalendarUnavailable.NO_CONNECTOR

    async def test_no_credentials(self) -> None:
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service(credentials=None)),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector())),
        ):
            async with open_active_calendar(MagicMock(), uuid4()) as access:
                assert access is CalendarUnavailable.NO_CREDENTIALS

    async def test_no_client_class_for_that_provider(self) -> None:
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=_connector())),
            patch(_REGISTRY) as registry,
        ):
            registry.get_client_class.return_value = None

            async with open_active_calendar(MagicMock(), uuid4()) as access:
                assert access is CalendarUnavailable.NO_CLIENT

    async def test_nothing_is_closed_when_nothing_was_opened(self) -> None:
        """A close on a client that was never built would be an AttributeError
        inside a ``finally`` — the worst possible place for one."""
        with (
            patch(_CONNECTOR_SERVICE, return_value=_service()),
            patch(_RESOLVE, new=AsyncMock(return_value=None)),
        ):
            async with open_active_calendar(MagicMock(), uuid4()) as access:
                assert isinstance(access, CalendarUnavailable)
