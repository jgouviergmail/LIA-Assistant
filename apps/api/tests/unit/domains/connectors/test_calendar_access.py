"""Opening the person's calendar, once, for every surface that needs it.

The same eight lines — resolve the active connector, fetch the right shape of
credentials, look up the client class, resolve the owner's default calendar,
close the transport — were written in ``ContextAggregator._fetch_calendar`` and
in ``briefing.fetchers.fetch_agenda``, and had already DIVERGED (one closed its
transport, the other never did). ADR-304 moved the opening itself to the shared
door (``connectors.active_client``, tested there: the transport closed on every
path, Apple's credentials, every named refusal, no session held); what is left
here is the calendar's own step — the OWNER's configured calendar, resolved on
the network once the door has read its name.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors import calendar_access
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.calendar_access import (
    CalendarAccess,
    CalendarUnavailable,
    open_active_calendar,
)
from src.domains.connectors.preferences.owner_defaults import CALENDAR

pytestmark = pytest.mark.unit


def _door(opened: Any) -> Any:
    @contextlib.asynccontextmanager
    async def _open(category: str, user_id: Any, *, container: Any = None) -> AsyncIterator[Any]:
        assert (category, container) == ("calendar", CALENDAR)
        yield opened

    return _open


async def test_it_yields_the_client_and_the_owners_configured_calendar() -> None:
    client = MagicMock()
    connector_type = MagicMock()
    owner = uuid4()
    resolve = AsyncMock(return_value="work@group.calendar")
    with (
        patch.object(
            calendar_access,
            "open_active_client",
            _door(
                ActiveClient(client=client, connector_type=connector_type, preferred_name="Work")
            ),
        ),
        patch.object(calendar_access, "resolve_owner_container_id", resolve),
    ):
        async with open_active_calendar(owner) as access:
            assert isinstance(access, CalendarAccess)
            assert access.client is client
            assert access.calendar_id == "work@group.calendar"
            assert access.connector_type is connector_type
    resolve.assert_awaited_once_with(client=client, name="Work", owner_id=owner, container=CALENDAR)


@pytest.mark.parametrize("reason", list(ClientUnavailable))
async def test_every_refusal_passes_through_named(reason: ClientUnavailable) -> None:
    """« Connect a calendar » and « your connection expired » stay two sentences."""
    resolve = AsyncMock()
    with (
        patch.object(calendar_access, "open_active_client", _door(reason)),
        patch.object(calendar_access, "resolve_owner_container_id", resolve),
    ):
        async with open_active_calendar(uuid4()) as access:
            assert access is reason
            assert isinstance(access, CalendarUnavailable)
    resolve.assert_not_awaited()
