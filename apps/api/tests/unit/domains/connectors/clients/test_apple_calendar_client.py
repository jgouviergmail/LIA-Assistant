"""Unit tests for AppleCalendarClient timezone handling.

Regression coverage for the 2026-07 codebase audit (wave 1):
- ``_parse_iso_datetime`` stamped UTC on naive datetimes, then
  ``_apply_timezone`` ignored timezone-aware values, so the ``timezone``
  parameter of create/update was NEVER applied: an event created at
  "10:00 Europe/Paris" was stored at 10:00 UTC (12:00 Paris in summer).

The same defect came back on another provider in 2026-11, so the client is no
longer handed text to interpret (ADR-380): it takes bounds whose wall times
carry their zone, and ``_parse_iso_datetime`` reads search bounds only.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.connectors.clients.apple_calendar_client import (
    AppleCalendarClient,
    _parse_iso_datetime,
)
from src.domains.connectors.clients.event_bounds import bounds_of, change_of

PARIS = ZoneInfo("Europe/Paris")

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """AppleCalendarClient with mocked credentials and service (no network)."""
    return AppleCalendarClient(
        user_id=uuid4(),
        credentials=MagicMock(),
        connector_service=MagicMock(),
    )


@pytest.fixture
def mock_calendar():
    """CalDAV calendar mock whose save_event captures kwargs."""
    calendar = MagicMock()
    saved_event = MagicMock()
    saved_event.vobject_instance = None
    calendar.save_event = AsyncMock(return_value=saved_event)
    return calendar


# ============================================================================
# REGRESSION: requested timezone must reach the iCal component (audit item 6)
# ============================================================================


@pytest.mark.unit
async def test_create_event_applies_requested_timezone(client, mock_calendar):
    """create_event 10:00 Europe/Paris -> dtstart is 10:00 Paris, not 10:00 UTC."""
    with (
        patch.object(client, "_get_calendar", AsyncMock(return_value=mock_calendar)),
        patch(
            "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
            return_value={},
        ),
    ):
        await client._create_event_impl(
            summary="Dentiste",
            bounds=bounds_of("2026-07-10T10:00:00", "2026-07-10T11:00:00", PARIS, all_day=False),
            description=None,
            location=None,
            attendees=None,
            calendar_id="primary",
            uid="fixed-uid",
        )

    kwargs = mock_calendar.save_event.await_args.kwargs
    expected_start = datetime(2026, 7, 10, 10, 0, tzinfo=PARIS)
    expected_end = datetime(2026, 7, 10, 11, 0, tzinfo=PARIS)
    assert kwargs["dtstart"] == expected_start
    assert str(kwargs["dtstart"].tzinfo) == "Europe/Paris"
    assert kwargs["dtend"] == expected_end


@pytest.mark.unit
async def test_create_event_keeps_the_instant_an_offset_names(client, mock_calendar):
    """A time written with an offset is an instant: stored at it, on the person's wall."""
    with (
        patch.object(client, "_get_calendar", AsyncMock(return_value=mock_calendar)),
        patch(
            "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
            return_value={},
        ),
    ):
        await client._create_event_impl(
            summary="Call NYC",
            bounds=bounds_of(
                "2026-07-10T10:00:00-04:00", "2026-07-10T11:00:00-04:00", PARIS, all_day=False
            ),
            description=None,
            location=None,
            attendees=None,
            calendar_id="primary",
            uid="fixed-uid",
        )

    kwargs = mock_calendar.save_event.await_args.kwargs
    # Ten in New York is 14:00 UTC, four in the afternoon on a Paris wall in summer.
    assert kwargs["dtstart"].astimezone(UTC) == datetime(2026, 7, 10, 14, 0, tzinfo=UTC)
    assert str(kwargs["dtstart"].tzinfo) == "Europe/Paris"
    assert (kwargs["dtstart"].hour, kwargs["dtend"].hour) == (16, 17)


@pytest.mark.unit
async def test_update_event_applies_requested_timezone(client):
    """update_event with a new start at 09:00 Europe/Paris stores 09:00 Paris."""
    vevent = MagicMock()
    target_event = MagicMock()
    target_event.vobject_instance.vevent = vevent
    target_event.save = AsyncMock()

    with (
        patch.object(client, "_get_calendar", AsyncMock(return_value=MagicMock())),
        patch.object(client, "_find_event_by_uid", AsyncMock(return_value=target_event)),
        patch(
            "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
            return_value={},
        ),
    ):
        await client._update_event_impl(
            event_id="uid-123",
            summary=None,
            bounds=change_of("2026-07-10T09:00:00", None, PARIS, all_day=None),
            description=None,
            location=None,
            attendees=None,
            calendar_id="primary",
        )

    assert vevent.dtstart.value == datetime(2026, 7, 10, 9, 0, tzinfo=PARIS)
    assert str(vevent.dtstart.value.tzinfo) == "Europe/Paris"


# ============================================================================
# Helper contracts
# ============================================================================


@pytest.mark.unit
def test_parse_iso_datetime_stamps_utc_on_a_search_bound():
    """A search bound that names no offset is read as UTC."""
    assert _parse_iso_datetime("2026-07-10T10:00:00") == datetime(2026, 7, 10, 10, 0, tzinfo=UTC)


@pytest.mark.unit
def test_parse_iso_datetime_preserves_explicit_offset():
    """An explicit offset in the string is preserved."""
    parsed = _parse_iso_datetime("2026-07-10T10:00:00+02:00")
    assert parsed.utcoffset().total_seconds() == 2 * 3600
