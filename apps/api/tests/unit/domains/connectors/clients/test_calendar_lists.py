"""Which calendars a reader of the person's meetings reads (owner rule 2026-11-15).

Every calendar the account OWNS, the configured default first whatever its role;
never a calendar someone else shares. The listing is asked whole, because its
order is the provider's, and a calendar left unread is said, never guessed.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.constants import CALENDAR_LIST_PAGE_MAX, CALENDAR_READ_CONCURRENCY
from src.domains.connectors.clients.calendar_lists import (
    calendar_ref,
    calendars_to_read,
    is_owned,
    merge_calendar_events,
    owned_calendar_by_ref,
    read_calendar_windows,
    read_owned_events,
    unread_in_freebusy,
)

pytestmark = pytest.mark.unit


def _client(items: list[Any], *, truncated: bool = False) -> AsyncMock:
    client = AsyncMock()
    client.list_calendars.return_value = {"items": items, "truncated": truncated}
    return client


class TestOwned:
    @pytest.mark.parametrize(
        ("calendar", "owned"),
        [
            ({"id": "x", "accessRole": "owner"}, True),
            ({"id": "x", "accessRole": "writer"}, False),
            ({"id": "x", "accessRole": "reader"}, False),
            ({"id": "x", "accessRole": "freeBusyReader"}, False),
            # CalDAV publishes no role: its calendar home is the account's own.
            ({"id": "x"}, True),
        ],
    )
    def test_the_provider_s_word_decides(self, calendar: dict[str, Any], owned: bool) -> None:
        assert is_owned(calendar) is owned


class TestCalendarsToRead:
    async def test_the_default_first_then_every_owned_calendar(self) -> None:
        client = _client(
            [
                {"id": "moi@x.com", "accessRole": "owner", "primary": True},
                {"id": "voisin@x.com", "accessRole": "writer"},
                {"id": "voyages", "accessRole": "owner"},
                {"id": "agenda-perso", "accessRole": "owner"},
                {"id": "feries", "accessRole": "reader"},
            ]
        )
        read = await calendars_to_read(client, "agenda-perso", bound=25)
        assert read.ids == ["agenda-perso", "moi@x.com", "voyages"]
        assert read.cut is False

    async def test_asks_the_whole_listing_before_keeping_the_owned(self) -> None:
        """« The first N » of a listing whose order is the provider's drops an owned one."""
        client = _client([])
        await calendars_to_read(client, "primary", bound=3)
        client.list_calendars.assert_awaited_once_with(max_results=CALENDAR_LIST_PAGE_MAX)

    async def test_an_owned_calendar_listed_after_many_shared_ones_is_read(self) -> None:
        shared = [{"id": f"collegue-{index}", "accessRole": "reader"} for index in range(40)]
        client = _client([*shared, {"id": "mien", "accessRole": "owner"}])
        read = await calendars_to_read(client, "primary", bound=25)
        assert read.ids == ["primary", "mien"]
        assert read.cut is False

    async def test_a_default_someone_shares_is_still_read(self) -> None:
        client = _client(
            [
                {"id": "moi@x.com", "accessRole": "owner", "primary": True},
                {"id": "famille", "accessRole": "writer"},
            ]
        )
        read = await calendars_to_read(client, "famille", bound=25)
        assert read.ids == ["famille", "moi@x.com"]

    async def test_primary_names_the_main_calendar_the_listing_has(self) -> None:
        """Read by alias AND by id, the main calendar would be read twice."""
        client = _client(
            [
                {"id": "voyages", "accessRole": "owner"},
                {"id": "moi@x.com", "accessRole": "owner", "primary": True},
            ]
        )
        read = await calendars_to_read(client, "primary", bound=25)
        assert read.ids == ["moi@x.com", "voyages"]

    async def test_primary_stays_the_alias_when_no_main_calendar_is_listed(self) -> None:
        client = _client([{"id": "voyages", "accessRole": "owner"}])
        read = await calendars_to_read(client, "primary", bound=25)
        assert read.ids == ["primary", "voyages"]

    async def test_an_empty_listing_still_reads_the_default(self) -> None:
        read = await calendars_to_read(_client([]), "agenda-perso", bound=25)
        assert read.ids == ["agenda-perso"]
        assert read.cut is False

    async def test_past_the_bound_the_default_is_kept_and_the_cut_said(self) -> None:
        owned = [{"id": f"agenda-{index}", "accessRole": "owner"} for index in range(5)]
        read = await calendars_to_read(_client(owned), "agenda-4", bound=3)
        assert read.ids == ["agenda-4", "agenda-0", "agenda-1"]
        assert read.cut is True

    async def test_exactly_the_bound_is_no_cut(self) -> None:
        owned = [{"id": f"agenda-{index}", "accessRole": "owner"} for index in range(3)]
        read = await calendars_to_read(_client(owned), "agenda-0", bound=3)
        assert read.cut is False

    async def test_a_listing_the_provider_cut_is_said(self) -> None:
        client = _client([{"id": "agenda-perso", "accessRole": "owner"}], truncated=True)
        read = await calendars_to_read(client, "agenda-perso", bound=25)
        assert read.ids == ["agenda-perso"]
        assert read.cut is True

    async def test_an_entry_without_an_id_is_never_read(self) -> None:
        client = _client(
            ["not a calendar", {"accessRole": "owner"}, {"id": "", "accessRole": "owner"}]
        )
        read = await calendars_to_read(client, "agenda-perso", bound=25)
        assert read.ids == ["agenda-perso"]


class TestReadCalendarWindows:
    """The windows of every owned calendar, a few at a time, on one client."""

    async def test_each_answer_comes_back_beside_its_calendar_in_the_order_asked(self) -> None:
        client = AsyncMock()

        async def window(calendar_id: str, time_min: str, *_: Any, **__: Any) -> dict[str, Any]:
            return {"events": [{"id": f"{calendar_id}@{time_min}"}], "truncated": False}

        client.list_events_window.side_effect = window
        answers = await read_calendar_windows(
            client, [("a", "t1", "t2"), ("b", "t1", "t2"), ("a", "t0", "t1")], bound=5
        )
        assert [(calendar, answer["events"][0]["id"]) for calendar, answer in answers] == [
            ("a", "a@t1"),
            ("b", "b@t1"),
            ("a", "a@t0"),
        ]
        assert {call.kwargs["bound"] for call in client.list_events_window.await_args_list} == {5}

    async def test_no_more_reads_run_at_once_than_the_concurrency(self) -> None:
        running = peak = 0
        client = AsyncMock()

        async def window(*_: Any, **__: Any) -> dict[str, Any]:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            running -= 1
            return {"events": [], "truncated": False}

        client.list_events_window.side_effect = window
        reads = [(f"agenda-{index}", "t0", "t1") for index in range(CALENDAR_READ_CONCURRENCY * 3)]
        await read_calendar_windows(client, reads, bound=5)
        assert peak == CALENDAR_READ_CONCURRENCY

    async def test_a_failed_read_is_raised_as_itself_its_siblings_cancelled(self) -> None:
        """A handler that knows the provider's failure must see it, not a group."""
        slow_started = asyncio.Event()
        cancelled: list[str] = []
        client = AsyncMock()

        async def window(calendar_id: str, *_: Any, **__: Any) -> dict[str, Any]:
            if calendar_id == "down":
                await slow_started.wait()
                raise ConnectionError("calendar down")
            slow_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(calendar_id)
                raise
            raise AssertionError("never answered")

        client.list_events_window.side_effect = window
        with pytest.raises(ConnectionError):
            await read_calendar_windows(
                client, [("slow", "t0", "t1"), ("down", "t0", "t1")], bound=5
            )
        assert cancelled == ["slow"]


class TestMergeCalendarEvents:
    def test_a_meeting_two_calendars_hold_is_kept_once_with_the_first(self) -> None:
        events, calendar_of = merge_calendar_events(
            [
                ("famille", {"events": [{"id": "m", "summary": "first"}]}),
                ("main", {"events": [{"id": "m", "summary": "second"}, {"id": "n"}]}),
            ]
        )
        assert [(event["id"], event.get("summary")) for event in events] == [
            ("m", "first"),
            ("n", None),
        ]
        assert calendar_of == {"m": "famille", "n": "main"}

    def test_an_event_without_an_id_is_never_matched_by_guesswork(self) -> None:
        events, calendar_of = merge_calendar_events(
            [("a", {"events": [{"summary": "x"}, "not an event"]}), ("b", {"events": [{}]})]
        )
        assert len(events) == 2
        assert calendar_of == {}


class TestReadOwnedEvents:
    @staticmethod
    def _client(held: dict[str, list[dict[str, Any]]], *, truncated: bool = False) -> AsyncMock:
        client = _client([{"id": key, "accessRole": "owner"} for key in held])

        async def window(calendar_id: str, time_min: str, *_: Any, **__: Any) -> dict[str, Any]:
            return {
                "events": [{**e, "span": time_min} for e in held.get(calendar_id, [])],
                "truncated": truncated,
            }

        client.list_events_window.side_effect = window
        return client

    async def test_every_span_is_asked_of_every_owned_calendar(self) -> None:
        client = self._client({"famille": [{"id": "f"}], "main": [{"id": "m"}]})
        owned = await read_owned_events(client, "famille", [("t0", "t1"), ("t2", "t3")], bound=9)
        asked = [call.args[:2] for call in client.list_events_window.await_args_list]
        assert asked == [("famille", "t0"), ("famille", "t2"), ("main", "t0"), ("main", "t2")]
        assert owned.calendars == ["famille", "main"]
        assert owned.calendar_of == {"f": "famille", "m": "main"}
        assert owned.cut is False

    async def test_a_cut_window_or_a_cut_listing_is_said(self) -> None:
        cut_window = self._client({"a": []}, truncated=True)
        assert (await read_owned_events(cut_window, "a", [("t0", "t1")], bound=9)).cut
        client = _client([{"id": "a", "accessRole": "owner"}], truncated=True)
        client.list_events_window.return_value = {"events": [], "truncated": False}
        assert (await read_owned_events(client, "a", [("t0", "t1")], bound=9)).cut

    async def test_a_projection_is_asked_only_when_given(self) -> None:
        client = self._client({"a": []})
        await read_owned_events(client, "a", [("t0", "t1")], bound=9)
        await read_owned_events(client, "a", [("t0", "t1")], bound=9, fields=["id"])
        first, second = client.list_events_window.await_args_list
        assert "fields" not in first.kwargs
        assert second.kwargs["fields"] == ["id"]


class TestUnreadInFreebusy:
    def test_a_calendar_answered_with_errors_was_not_read(self) -> None:
        response = {"calendars": {"a": {"busy": []}, "b": {"errors": [{"reason": "x"}]}}}
        assert unread_in_freebusy(response, ["a", "b"]) is True

    def test_a_calendar_missing_from_the_answer_was_not_read(self) -> None:
        assert unread_in_freebusy({"calendars": {"a": {"busy": []}}}, ["a", "b"]) is True

    def test_every_calendar_answered_is_a_whole_read(self) -> None:
        response = {"calendars": {"a": {"busy": []}, "b": {"busy": [{"start": "x"}]}}}
        assert unread_in_freebusy(response, ["a", "b"]) is False


class TestCalendarRef:
    def test_a_calendar_is_kept_as_a_digest_never_its_address(self) -> None:
        ref = calendar_ref("moi@example.com")
        assert ref == calendar_ref("moi@example.com")
        assert len(ref) == 16 and "@" not in ref
        assert ref != calendar_ref("famille@group.calendar.google.com")

    async def test_the_digest_finds_an_owned_calendar_again_or_nothing(self) -> None:
        client = _client([{"id": "moi@example.com", "accessRole": "owner", "primary": True}])
        found = await owned_calendar_by_ref(client, "primary", calendar_ref("moi@example.com"))
        gone = await owned_calendar_by_ref(client, "primary", calendar_ref("parti@example.com"))
        assert (found, gone) == ("moi@example.com", None)
