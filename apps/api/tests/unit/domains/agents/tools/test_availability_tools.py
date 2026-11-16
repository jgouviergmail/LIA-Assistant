"""Find-availability tool (lot B, 2026-08).

Pinned behaviors:
- Google path uses the freeBusy endpoint (busy ranges only — strictly less
  data than fetching events);
- providers without freeBusy (Apple/Microsoft) fall back to the same
  minimized events projection availability already used (start/end only);
- EVERY calendar the account owns is read, the configured default first (owner
  rule 2026-11-15): a meeting in the main calendar makes the person busy
  whichever calendar they create in; a calendar someone else shares never counts;
- a calendar Google could not read, or one left unread, is never « free »: the
  model is told a slot may be booked;
- the returned totals are exact (count doctrine), slots are ISO datetimes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import availability_tools as availability_tools_module
from src.domains.agents.tools.availability_tools import FindAvailabilityTool
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient

pytestmark = pytest.mark.unit

_WINDOW = {
    "start_datetime": "2026-08-27T09:00:00",
    "end_datetime": "2026-08-27T17:00:00",
}
#: The account's main calendar, under the id Google lists it by.
_MAIN = "moi@x.com"
_TEN_TO_ELEVEN = {"start": "2026-08-27T10:00:00Z", "end": "2026-08-27T11:00:00Z"}


def _tool() -> FindAvailabilityTool:
    tool = FindAvailabilityTool()
    tool.runtime = MagicMock()
    return tool


def _patch_prefs() -> Any:
    return patch(
        "src.domains.agents.tools.runtime_helpers.get_user_preferences",
        new=AsyncMock(return_value=("UTC", "fr", None)),
    )


def _patch_default(calendar_id: str) -> Any:
    return patch(
        "src.domains.connectors.preferences.owner_defaults.resolve_owner_calendar_id",
        new=AsyncMock(return_value=calendar_id),
    )


def _google(
    busy: dict[str, list[dict[str, str]]],
    *,
    listing: list[dict[str, Any]] | None = None,
    errors: tuple[str, ...] = (),
    listing_cut: bool = False,
) -> MagicMock:
    """A Google client: a calendar listing, and freeBusy echoing every calendar asked."""
    client = MagicMock(spec=GoogleCalendarClient)
    client.connector_service = MagicMock()
    client.connector_type = "google_calendar"
    listed = (
        [{"id": key, "accessRole": "owner", "primary": key == _MAIN} for key in busy]
        if listing is None
        else listing
    )
    client.list_calendars = AsyncMock(return_value={"items": listed, "truncated": listing_cut})

    async def freebusy(*, time_min: str, time_max: str, calendar_ids: list[str]) -> dict[str, Any]:
        answered: dict[str, Any] = {}
        for calendar_id in calendar_ids:
            if calendar_id in errors:
                answered[calendar_id] = {"errors": [{"reason": "notFound"}], "busy": []}
            else:
                answered[calendar_id] = {"busy": busy.get(calendar_id, [])}
        return {"calendars": answered}

    client.query_freebusy = AsyncMock(side_effect=freebusy)
    return client


def _projection(
    events: dict[str, list[dict[str, Any]]],
    *,
    truncated: bool = False,
    listing: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """A provider without freeBusy (CalDAV: its listing names no role)."""
    client = MagicMock(
        spec=["list_calendars", "list_events_window", "connector_service", "connector_type"]
    )
    client.connector_type = "apple_calendar"
    client.connector_service = MagicMock()
    listed = (
        [{"id": key, "primary": index == 0} for index, key in enumerate(events)]
        if listing is None
        else listing
    )
    client.list_calendars = AsyncMock(return_value={"items": listed, "truncated": False})

    async def window(
        calendar_id: str,
        time_min: str,
        time_max: str,
        *,
        bound: int,
        fields: list[str] | None = None,
    ) -> Any:
        return {"events": events.get(calendar_id, []), "truncated": truncated}

    client.list_events_window = AsyncMock(side_effect=window)
    return client


def _busy_event(start: str, end: str) -> dict[str, Any]:
    return {"start": {"dateTime": start}, "end": {"dateTime": end}}


async def _run(client: MagicMock, default: str = "primary", **kwargs: Any) -> dict[str, Any]:
    with _patch_prefs(), _patch_default(default):
        result: dict[str, Any] = await _tool().execute_api_call(
            client, uuid4(), **{**_WINDOW, **kwargs}
        )
    return result


class TestFreeBusyPath:
    async def test_google_client_uses_freebusy_and_returns_exact_slots(self) -> None:
        client = _google(
            {
                _MAIN: [
                    _TEN_TO_ELEVEN,
                    {"start": "2026-08-27T14:00:00Z", "end": "2026-08-27T15:00:00Z"},
                ]
            }
        )

        result = await _run(client, duration_minutes=60, working_hours_only=False)

        client.query_freebusy.assert_awaited_once()
        assert result["success"] is True
        assert result["total"] == 3
        assert result["busy_count"] == 2
        assert result["slots"][0]["start"] == "2026-08-27T09:00:00+00:00"
        assert result["slots"][0]["end"] == "2026-08-27T10:00:00+00:00"
        assert result["window_complete"] is True

    async def test_provider_without_freebusy_reads_the_whole_window(self) -> None:
        client = _projection(
            {"home": [_busy_event("2026-08-27T10:00:00Z", "2026-08-27T16:00:00Z")]}
        )

        result = await _run(client, duration_minutes=30, working_hours_only=False)

        client.list_events_window.assert_awaited_once()
        # Every event of the window, pages drained, under the projection's bound.
        assert (
            client.list_events_window.call_args.kwargs["bound"]
            == availability_tools_module.AVAILABILITY_PROJECTION_MAX_EVENTS
        )
        # Busy ranges only: start and end are all a provider is asked for.
        assert client.list_events_window.call_args.kwargs["fields"] == ["start", "end"]
        assert result["success"] is True
        assert result["total"] == 2  # 09-10 and 16-17
        assert result["window_complete"] is True

    async def test_a_busy_window_read_in_part_reaches_the_model_as_incomplete(self) -> None:
        """A cut busy list would offer a booked slot as free: the model is told."""
        result = await _run(_projection({"home": []}, truncated=True))

        assert result["window_complete"] is False
        output = _tool().format_registry_response(result)
        assert output.structured_data["window_complete"] is False
        assert "a slot may be booked" in output.message

    async def test_a_whole_window_says_nothing_of_a_cut(self) -> None:
        result = await _run(_projection({"home": []}))

        assert "may be booked" not in _tool().format_registry_response(result).message

    async def test_duration_is_mechanically_clamped(self) -> None:
        """Repair-before-validate: an absurd duration is clamped, not rejected."""
        result = await _run(_google({_MAIN: []}), duration_minutes=100000, working_hours_only=False)

        # Window is 8h: a clamped (<= 480 min) duration still fits, so the
        # whole free window comes back as one slot instead of an empty answer.
        assert result["total"] == 1


class TestEveryOwnedCalendar:
    """The defect of 2026-11-15: an invitation in the main calendar left the slot « free »."""

    async def test_a_meeting_in_the_main_calendar_makes_the_slot_busy(self) -> None:
        client = _google(
            {_MAIN: [_TEN_TO_ELEVEN], "famille": []},
            listing=[
                {"id": _MAIN, "accessRole": "owner", "primary": True},
                {"id": "famille", "accessRole": "owner"},
            ],
        )

        result = await _run(client, "famille", duration_minutes=60, working_hours_only=False)

        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == ["famille", _MAIN]
        assert result["busy_count"] == 1
        assert "2026-08-27T10:00:00+00:00" not in [slot["start"] for slot in result["slots"]]

    async def test_a_calendar_someone_else_shares_never_counts(self) -> None:
        client = _google(
            {_MAIN: [], "collegue@x.com": [_TEN_TO_ELEVEN]},
            listing=[
                {"id": _MAIN, "accessRole": "owner", "primary": True},
                {"id": "collegue@x.com", "accessRole": "reader"},
            ],
        )

        result = await _run(client, duration_minutes=60, working_hours_only=False)

        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == [_MAIN]
        assert result["busy_count"] == 0

    async def test_a_calendar_google_could_not_read_is_never_free(self) -> None:
        """Google answers an unreadable calendar with errors and NO busy block."""
        client = _google({_MAIN: [], "famille": []}, errors=(_MAIN,))

        result = await _run(client, "famille")

        assert result["window_complete"] is False
        assert "a slot may be booked" in _tool().format_registry_response(result).message

    async def test_calendars_left_unread_are_said(self) -> None:
        result = await _run(_google({_MAIN: []}, listing_cut=True))

        assert result["window_complete"] is False

    async def test_the_projection_reads_every_owned_calendar(self) -> None:
        client = _projection(
            {
                "home": [_busy_event("2026-08-27T09:00:00Z", "2026-08-27T12:00:00Z")],
                "work": [_busy_event("2026-08-27T13:00:00Z", "2026-08-27T17:00:00Z")],
            }
        )

        result = await _run(client, duration_minutes=60, working_hours_only=False)

        assert {call.args[0] for call in client.list_events_window.await_args_list} == {
            "home",
            "work",
        }
        assert [(slot["start"], slot["end"]) for slot in result["slots"]] == [
            ("2026-08-27T12:00:00+00:00", "2026-08-27T13:00:00+00:00")
        ]


class TestTheOwnersDefaultCalendarIsHonoured:
    """Availability reads the calendar the owner CONFIGURED first, never `primary` alone.

    The defect `owner_defaults.py` was written to close, found here on the
    owner's own path: both branches queried `primary` unconditionally, so a
    user whose agenda lives in a named calendar ("Famille", "Travail") was
    reported FREE while they were busy — the same 2026-07-30 measurement that
    module's docstring cites, pointing at the account itself instead of a peer.
    """

    async def test_the_freebusy_path_asks_the_configured_calendar(self) -> None:
        client = _google({_MAIN: [], "famille@group.calendar.google.com": []})

        await _run(client, "famille@group.calendar.google.com")

        assert client.query_freebusy.call_args.kwargs["calendar_ids"][0] == (
            "famille@group.calendar.google.com"
        )

    async def test_the_projection_fallback_asks_it_too(self) -> None:
        client = _projection({"home": []})

        await _run(client, "Travail")

        assert client.list_events_window.await_args_list[0].args[0] == "Travail"

    async def test_an_unset_preference_still_reads_primary(self) -> None:
        """The degradation the resolver already documents, unchanged."""
        client = _google({}, listing=[])

        await _run(client, "primary")

        assert client.query_freebusy.call_args.kwargs["calendar_ids"] == ["primary"]

    async def test_a_failing_resolution_does_not_lose_the_answer(self) -> None:
        """Availability degrades to `primary` rather than failing the turn.

        Deliberately different from the WRITE paths: creating an event in the
        wrong calendar is a mistake in the world, while reading availability
        from `primary` is a stated fallback the resolver already makes.
        """
        client = _google({}, listing=[])

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
