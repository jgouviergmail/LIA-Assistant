"""Find-availability tool (lot B, 2026-08).

Pinned behaviors:
- Google path uses the freeBusy endpoint (busy ranges only — strictly less
  data than fetching events);
- providers without freeBusy (Apple/Microsoft) fall back to the same
  minimized events projection availability already used (start/end only);
- the returned totals are exact (count doctrine), slots are ISO datetimes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.availability_tools import FindAvailabilityTool
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient

pytestmark = pytest.mark.unit

_WINDOW = {
    "start_datetime": "2026-08-27T09:00:00",
    "end_datetime": "2026-08-27T17:00:00",
}


def _tool() -> FindAvailabilityTool:
    tool = FindAvailabilityTool()
    tool.runtime = MagicMock()
    return tool


def _patch_prefs() -> Any:
    return patch(
        "src.domains.agents.tools.runtime_helpers.get_user_preferences",
        new=AsyncMock(return_value=("UTC", "fr", None)),
    )


class TestFreeBusyPath:
    async def test_google_client_uses_freebusy_and_returns_exact_slots(self) -> None:
        client = MagicMock(spec=GoogleCalendarClient)
        client.query_freebusy = AsyncMock(
            return_value={
                "calendars": {
                    "primary": {
                        "busy": [
                            {"start": "2026-08-27T10:00:00Z", "end": "2026-08-27T11:00:00Z"},
                            {"start": "2026-08-27T14:00:00Z", "end": "2026-08-27T15:00:00Z"},
                        ]
                    }
                }
            }
        )

        with _patch_prefs():
            result = await _tool().execute_api_call(
                client,
                uuid4(),
                **_WINDOW,
                duration_minutes=60,
                working_hours_only=False,
            )

        client.query_freebusy.assert_awaited_once()
        assert result["success"] is True
        assert result["total"] == 3
        assert result["busy_count"] == 2
        assert result["slots"][0]["start"] == "2026-08-27T09:00:00+00:00"
        assert result["slots"][0]["end"] == "2026-08-27T10:00:00+00:00"

    async def test_provider_without_freebusy_falls_back_to_events_projection(self) -> None:
        client = MagicMock(spec=["list_events"])
        client.list_events = AsyncMock(
            return_value={
                "items": [
                    {
                        "start": {"dateTime": "2026-08-27T10:00:00Z"},
                        "end": {"dateTime": "2026-08-27T16:00:00Z"},
                    }
                ]
            }
        )

        with _patch_prefs():
            result = await _tool().execute_api_call(
                client,
                uuid4(),
                **_WINDOW,
                duration_minutes=30,
                working_hours_only=False,
            )

        client.list_events.assert_awaited_once()
        # Minimization: the projection must request start/end fields only.
        assert client.list_events.call_args.kwargs["fields"] == ["start", "end"]
        assert result["success"] is True
        assert result["total"] == 2  # 09-10 and 16-17

    async def test_duration_is_mechanically_clamped(self) -> None:
        """Repair-before-validate: an absurd duration is clamped, not rejected."""
        client = MagicMock(spec=GoogleCalendarClient)
        client.query_freebusy = AsyncMock(return_value={"calendars": {}})

        with _patch_prefs():
            result = await _tool().execute_api_call(
                client,
                uuid4(),
                **_WINDOW,
                duration_minutes=100000,
                working_hours_only=False,
            )

        # Window is 8h: a clamped (<= 480 min) duration still fits, so the
        # whole free window comes back as one slot instead of an empty answer.
        assert result["total"] == 1


class TestTheOwnersDefaultCalendarIsHonoured:
    """Availability reads the calendar the owner CONFIGURED, not `primary`.

    The defect `owner_defaults.py` was written to close, found here on the
    owner's own path: both branches queried `primary` unconditionally, so a
    user whose agenda lives in a named calendar ("Famille", "Travail") was
    reported FREE while they were busy — the same 2026-07-30 measurement that
    module's docstring cites, pointing at the account itself instead of a peer.

    Reported as a possible regression of the ADR-263 lot; verified factually
    to predate it (this file's last change is v1.31.1). Real defect either way.
    """

    @staticmethod
    def _patch_default(calendar_id: str) -> Any:
        return patch(
            "src.domains.connectors.preferences.owner_defaults.resolve_owner_calendar_id",
            new=AsyncMock(return_value=calendar_id),
        )

    async def test_the_freebusy_path_asks_the_configured_calendar(self) -> None:
        client = MagicMock(spec=GoogleCalendarClient)
        client.query_freebusy = AsyncMock(return_value={"calendars": {}})
        client.connector_service = MagicMock()
        client.connector_type = "google_calendar"

        with _patch_prefs(), self._patch_default("famille@group.calendar.google.com"):
            await _tool().execute_api_call(client, uuid4(), **_WINDOW)

        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == [
            "famille@group.calendar.google.com"
        ]

    async def test_the_projection_fallback_asks_it_too(self) -> None:
        client = MagicMock(spec=["list_events", "connector_service", "connector_type"])
        client.list_events = AsyncMock(return_value={"items": []})
        client.connector_service = MagicMock()
        client.connector_type = "apple_calendar"

        with _patch_prefs(), self._patch_default("Travail"):
            await _tool().execute_api_call(client, uuid4(), **_WINDOW)

        assert client.list_events.call_args.kwargs["calendar_id"] == "Travail"

    async def test_an_unset_preference_still_reads_primary(self) -> None:
        """The degradation the resolver already documents, unchanged."""
        client = MagicMock(spec=GoogleCalendarClient)
        client.query_freebusy = AsyncMock(return_value={"calendars": {}})
        client.connector_service = MagicMock()
        client.connector_type = "google_calendar"

        with _patch_prefs(), self._patch_default("primary"):
            await _tool().execute_api_call(client, uuid4(), **_WINDOW)

        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == ["primary"]

    async def test_a_failing_resolution_does_not_lose_the_answer(self) -> None:
        """Availability degrades to `primary` rather than failing the turn.

        Deliberately different from the WRITE paths: creating an event in the
        wrong calendar is a mistake in the world, while reading availability
        from `primary` is a stated fallback the resolver already makes.
        """
        client = MagicMock(spec=GoogleCalendarClient)
        client.query_freebusy = AsyncMock(return_value={"calendars": {}})
        client.connector_service = MagicMock()
        client.connector_type = "google_calendar"

        with (
            _patch_prefs(),
            patch(
                "src.domains.connectors.preferences.owner_defaults.resolve_owner_calendar_id",
                new=AsyncMock(side_effect=RuntimeError("connector unreachable")),
            ),
        ):
            result = await _tool().execute_api_call(client, uuid4(), **_WINDOW)

        assert result.get("success") is not False
        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == ["primary"]
