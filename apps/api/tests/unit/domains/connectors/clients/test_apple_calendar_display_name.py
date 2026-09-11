"""The display name of an async caldav Calendar is a coroutine, never a string.

Measured on production (2026-09-11, caldav 3.0.1): every
``GET /connectors/{id}/calendars`` on an Apple connector answered 500 with
``Input should be a valid string [input_type=coroutine]`` — ``Calendar.name`` is
a deprecated property delegating to ``get_display_name()``, which on an
``AsyncDAVClient`` RETURNS A COROUTINE even when the value sits in the props
cache. ``getattr(cal, "name", ...)`` therefore yields a coroutine (and a
``RuntimeWarning: coroutine ... was never awaited`` — 139 of them in 30 days),
and a default calendar chosen by NAME could never be matched.

These tests build their calendars from the PRODUCER — a real ``caldav.Calendar``
bound to a real ``AsyncDAVClient``, no network — so a fixture cannot invent a
contract the library does not have (a ``MagicMock`` with ``cal.name = "Personal"``
kept the unit suite green through the whole defect).
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from caldav.async_davclient import AsyncDAVClient
from caldav.collection import Calendar

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient

_CALDAV_URL = "https://caldav.example.invalid/"


@pytest.fixture
async def dav_client() -> AsyncIterator[AsyncDAVClient]:
    """A real async caldav client, never contacted, closed on its own loop."""
    async with AsyncDAVClient(url=_CALDAV_URL, username="u", password="p") as dav:
        yield dav


@pytest.fixture
def calendars(dav_client: AsyncDAVClient) -> list[Calendar]:
    """Two calendars exactly as ``get_calendars()`` builds them (name in the props cache)."""
    return [
        Calendar(client=dav_client, url=f"{_CALDAV_URL}1/calendars/home/", name="Personal"),
        Calendar(client=dav_client, url=f"{_CALDAV_URL}1/calendars/work/", name="Travail"),
    ]


@pytest.fixture
def client(calendars: list[Calendar]) -> AppleCalendarClient:
    """AppleCalendarClient whose principal lists the real calendars (no network)."""
    apple = AppleCalendarClient(
        user_id=uuid4(), credentials=MagicMock(), connector_service=MagicMock()
    )
    principal = MagicMock()
    principal.get_calendars = AsyncMock(return_value=calendars)
    apple._principal = principal
    return apple


@pytest.mark.unit
@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.filterwarnings("error::DeprecationWarning")
async def test_list_calendars_reads_the_display_name_as_a_string(
    client: AppleCalendarClient,
) -> None:
    """The summary is the calendar's display name, a plain ``str`` — never a coroutine."""
    result = await client._list_calendars_impl(max_results=10, show_hidden=False)

    summaries = [item["summary"] for item in result["items"]]
    assert summaries == ["Personal", "Travail"]
    assert all(isinstance(s, str) for s in summaries)
    assert result["items"][0]["primary"] is True
    assert result["items"][1]["primary"] is False


@pytest.mark.unit
@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.filterwarnings("error::DeprecationWarning")
async def test_get_calendar_matches_by_display_name(client: AppleCalendarClient) -> None:
    """A default calendar chosen by its NAME resolves to that calendar, not to an error."""
    calendar = await client._get_calendar("Travail")

    assert str(calendar.url).endswith("/calendars/work/")


@pytest.mark.unit
@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.filterwarnings("error::DeprecationWarning")
async def test_get_calendar_still_matches_by_url(client: AppleCalendarClient) -> None:
    """The URL match the client always had keeps working next to the name match."""
    calendar = await client._get_calendar(f"{_CALDAV_URL}1/calendars/work/")

    assert str(calendar.url).endswith("/calendars/work/")


@pytest.mark.unit
async def test_get_calendar_unknown_name_is_named_in_the_error(
    client: AppleCalendarClient,
) -> None:
    """An unknown name is refused with the name, never matched to the first calendar."""
    with pytest.raises(ValueError, match="Inexistant"):
        await client._get_calendar("Inexistant")


@pytest.mark.unit
@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.filterwarnings("error::DeprecationWarning")
async def test_list_events_logs_never_touch_the_deprecated_name(
    client: AppleCalendarClient, calendars: list[Calendar]
) -> None:
    """The debug log before the search reads the name through the same awaited door."""
    calendars[0].search = AsyncMock(return_value=[])

    with patch(
        "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
        return_value={},
    ):
        result = await client._list_events_impl(
            time_min=None,
            time_max=None,
            max_results=10,
            calendar_id="primary",
            query=None,
            fields=None,
        )

    assert result["items"] == []
