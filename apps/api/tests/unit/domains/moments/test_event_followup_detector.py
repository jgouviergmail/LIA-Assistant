"""Finding the meetings worth asking about, and refusing the rest.

The detector is where the feature becomes noise or becomes useful, so what is
pinned here is mostly what it REFUSES:

- **the block, not the slot.** Three meetings back to back are one afternoon.
  Filing three moments would spend three decisions and three quota slots to say
  one thing, and the anti-repeat window would only notice afterwards.
- **a meeting LIA recorded is already answered.** Its minutes reached the person
  when they were ready; asking on top of that reads as not having noticed.
- **a provider that blinks costs one pass, never the sweep.**
- **the fact is re-read before it is said**, because a moment is detected long
  before it is due and the world moves in between.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.domains.connectors.calendar_access import CalendarAccess, CalendarUnavailable
from src.domains.moments.detectors import event_followup

pytestmark = pytest.mark.unit

_MODULE = "src.domains.moments.detectors.event_followup"
NOW = datetime(2026, 9, 11, 16, 0, tzinfo=UTC)
UTC_TZ = ZoneInfo("UTC")
ME = "moi@example.com"


def _user() -> Any:
    return SimpleNamespace(id=uuid4(), email=ME, timezone="UTC")


def _event(
    *,
    ref: str = "evt-1",
    ended_minutes_ago: int = 30,
    duration: int = 60,
    guest_count: int = 2,
    anchor: datetime | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """A finished meeting that clears every necessary condition.

    ``anchor`` exists because the two code paths read time differently: the
    detector is HANDED ``now`` (so a frozen literal is right), while
    ``revalidate`` reads the real clock to decide whether the meeting has
    actually ended. An event built on a fixed literal in the future would read
    as « moved into the future » there, for ever.
    """
    base = anchor or NOW
    end = base - timedelta(minutes=ended_minutes_ago)
    start = end - timedelta(minutes=duration)
    guests = [{"email": ME, "responseStatus": "accepted"}] + [
        {"email": f"g{i}@example.com", "displayName": f"Guest{i}"} for i in range(guest_count - 1)
    ]
    event: dict[str, Any] = {
        "id": ref,
        "summary": "Point budget",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "location": "Salle Jaures",
        "attendees": guests,
        "organizer": {"email": "g1@example.com"},
    }
    event.update(overrides)
    return event


def _db_ctx() -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        yield MagicMock()

    return _ctx


def _calendar(items: list[dict[str, Any]] | Exception) -> Any:
    from contextlib import asynccontextmanager

    client = MagicMock()
    if isinstance(items, Exception):
        client.list_events = AsyncMock(side_effect=items)
    else:
        client.list_events = AsyncMock(return_value={"items": items})
    client.close = AsyncMock()

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

    return _open


def _no_calendar() -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarUnavailable.NO_CONNECTOR

    return _open


def _local(
    recorded: frozenset[str] = frozenset(),
    favorites: frozenset[str] = frozenset(),
    linked: frozenset[str] = frozenset(),
) -> Any:
    return AsyncMock(
        return_value=event_followup._LocalContext(
            recorded=recorded, favorites=favorites, linked=linked
        )
    )


async def _detect(
    items: list[dict[str, Any]] | Exception,
    *,
    opener: Any = None,
    local: Any = None,
) -> list[Any]:
    with (
        patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
        patch(f"{_MODULE}.open_active_calendar", new=opener or _calendar(items)),
        patch(f"{_MODULE}._local_context", new=local or _local()),
    ):
        return await event_followup.detect(_user(), NOW)


class TestWhenNothingIsFound:
    async def test_no_calendar_connector_files_nothing(self) -> None:
        assert await _detect([], opener=_no_calendar()) == []

    async def test_an_empty_window_files_nothing(self) -> None:
        assert await _detect([]) == []

    async def test_a_provider_failure_costs_one_pass_not_the_sweep(self) -> None:
        assert await _detect(RuntimeError("calendar down")) == []

    async def test_an_event_still_running_is_not_finished(self) -> None:
        """Google's timeMin filter is end-time based; an overlapping event slips
        through, and asking how a meeting went while it runs is absurd."""
        running = _event(ended_minutes_ago=-30)

        assert await _detect([running]) == []

    async def test_an_event_with_no_id_cannot_be_deduplicated(self) -> None:
        """Without an identity the same meeting would be filed at every pass."""
        anonymous = _event()
        anonymous.pop("id")

        assert await _detect([anonymous]) == []


class TestWhatIsFiled:
    async def test_a_worthy_meeting_becomes_a_candidate(self) -> None:
        [candidate] = await _detect([_event()])

        assert candidate.source_ref == "evt-1"
        assert candidate.kind == "event_followup"

    async def test_the_moment_falls_due_after_the_meeting_ends(self) -> None:
        end = NOW - timedelta(minutes=30)

        [candidate] = await _detect([_event(ended_minutes_ago=30)])

        assert candidate.due_at == end + timedelta(
            minutes=settings.moments_event_followup_delay_minutes
        )
        assert candidate.not_after == candidate.due_at + timedelta(
            minutes=settings.moments_event_followup_window_minutes
        )

    async def test_the_payload_carries_what_scoring_needs_and_no_one_else(self) -> None:
        """The revalidation re-reads the event, so storing the people would be
        personal data kept for nothing."""
        [candidate] = await _detect([_event()])

        assert set(candidate.payload) == {
            "title",
            "end",
            "score",
            "reasons",
            "attendee_count",
        }
        assert "Guest1" not in str(candidate.payload)
        assert "@" not in str(candidate.payload)

    async def test_an_unworthy_meeting_is_not_filed(self) -> None:
        """One attendee and no place: below the threshold."""
        thin = _event(guest_count=2)
        thin.pop("location")
        thin["organizer"] = {"email": "g1@example.com"}

        assert await _detect([thin]) == []


class TestTheBlockRule:
    async def test_a_meeting_followed_closely_by_another_files_nothing(self) -> None:
        """Only the last of a run carries the block."""
        first = _event(ref="a", ended_minutes_ago=90)
        second = _event(ref="b", ended_minutes_ago=30)

        refs = {c.source_ref for c in await _detect([first, second])}

        assert refs == {"b"}

    async def test_a_gap_wide_enough_makes_two_blocks(self) -> None:
        far_apart = settings.moments_event_chain_gap_minutes + 120
        first = _event(ref="a", ended_minutes_ago=30 + far_apart)
        second = _event(ref="b", ended_minutes_ago=30)

        refs = {c.source_ref for c in await _detect([first, second])}

        assert refs == {"a", "b"}

    async def test_a_solo_slot_does_not_break_a_block(self) -> None:
        """A focus block right after a meeting is not another meeting."""
        meeting = _event(ref="a", ended_minutes_ago=90)
        solo = _event(ref="b", ended_minutes_ago=30, guest_count=1)

        refs = {c.source_ref for c in await _detect([meeting, solo])}

        assert refs == {"a"}


class TestWhatIsAlreadyAnswered:
    async def test_a_meeting_lia_recorded_is_skipped(self) -> None:
        """Its minutes already reached the person."""
        detected = await _detect(
            [_event(ref="evt-rec")], local=_local(recorded=frozenset({"evt-rec"}))
        )

        assert detected == []


class TestRevalidation:
    @staticmethod
    def _live(**overrides: Any) -> dict[str, Any]:
        """An event anchored on the REAL clock — see ``_event``'s docstring."""
        return _event(anchor=datetime.now(UTC), **overrides)

    async def _revalidate(self, event: Any, *, opener: Any = None) -> Any:
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.open_active_calendar", new=opener or _reader(event)),
        ):
            return await event_followup.revalidate(_user(), "evt-1", {"title": "Point budget"})

    async def test_a_live_finished_meeting_is_still_worth_asking_about(self) -> None:
        facts = await self._revalidate(self._live())

        assert facts.still_valid is True
        assert any("Point budget" in line for line in facts.lines)

    async def test_a_cancelled_meeting_is_never_asked_about(self) -> None:
        facts = await self._revalidate(self._live(status="cancelled"))

        assert facts.still_valid is False

    async def test_a_meeting_moved_into_the_future_waits(self) -> None:
        """Moved while the moment waited: there is nothing to debrief yet, and
        the detector will file it again once it really ends."""
        facts = await self._revalidate(self._live(ended_minutes_ago=-120))

        assert facts.still_valid is False

    async def test_no_calendar_says_nothing(self) -> None:
        facts = await self._revalidate(self._live(), opener=_no_calendar())

        assert facts.still_valid is False

    async def test_a_provider_failure_says_nothing_rather_than_guessing(self) -> None:
        from contextlib import asynccontextmanager

        client = MagicMock()
        client.get_event = AsyncMock(side_effect=RuntimeError("gone"))
        client.close = AsyncMock()

        @asynccontextmanager
        async def _open(_db: Any, _user_id: Any):
            yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

        facts = await self._revalidate(self._live(), opener=_open)

        assert facts.still_valid is False

    async def test_the_lines_name_people_by_first_name_and_never_by_address(self) -> None:
        """The prompt needs enough to write « with Marc »; a full address in a
        prompt is personal data the sentence never uses."""
        facts = await self._revalidate(
            self._live(
                attendees=[
                    {"email": ME, "self": True},
                    {"email": "marc.dupont@example.com", "displayName": "Marc Dupont"},
                ]
            )
        )

        joined = " ".join(facts.lines)
        assert "Marc" in joined
        assert "Dupont" not in joined
        assert "@" not in joined


def _reader(event: dict[str, Any]) -> Any:
    from contextlib import asynccontextmanager

    client = MagicMock()
    client.get_event = AsyncMock(return_value=event)
    client.close = AsyncMock()

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

    return _open


class TestTheWindowTheChainRuleNeeds:
    """The chain rule can only break a block it can SEE.

    `is_chained` asks whether another meeting starts within the gap AFTER this
    one ends. The read used to stop at `now`, so a meeting that had not started
    yet was simply absent from the list — and the rule answered « nothing
    follows » about a block it could not see the end of.

    The consequence was not theoretical and not recoverable: a moment filed by
    an early pass is never un-filed (the insert is the only writer, and it
    conflicts rather than deletes), the revalidation re-reads ONE event and so
    cannot see a neighbour either, and a moment deliberately bypasses the
    in-meeting guard. LIA therefore asked « how did it go? » in the middle of
    the next meeting — the exact thing the block rule exists to prevent.

    The window must reach exactly as far ahead as the rule tests, and no
    further: everything beyond the gap is irrelevant to it.
    """

    @staticmethod
    async def _captured_window(items: list[dict[str, Any]]) -> dict[str, Any]:
        """The kwargs the detector really sent the provider."""
        from contextlib import asynccontextmanager

        client = MagicMock()
        client.list_events = AsyncMock(return_value={"items": items})
        client.close = AsyncMock()

        @asynccontextmanager
        async def _open(_db: Any, _user_id: Any):
            yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.open_active_calendar", new=_open),
            patch(f"{_MODULE}._local_context", new=_local()),
        ):
            await event_followup.detect(_user(), NOW)

        return dict(client.list_events.await_args.kwargs)

    async def test_the_read_reaches_the_chain_gap_beyond_now(self) -> None:
        kwargs = await self._captured_window([_event()])

        time_max = datetime.fromisoformat(kwargs["time_max"])
        gap = timedelta(minutes=settings.moments_event_chain_gap_minutes)
        assert time_max == NOW + gap

    async def test_it_still_starts_at_the_lookback(self) -> None:
        kwargs = await self._captured_window([_event()])

        time_min = datetime.fromisoformat(kwargs["time_min"])
        assert time_min == NOW - timedelta(minutes=settings.moments_detect_lookback_minutes)

    async def test_a_meeting_that_has_not_ended_earns_nothing_itself(self) -> None:
        """The widened window returns future events; they are chain breakers
        only, never candidates — a debrief of a meeting still running is absurd."""
        running = _event(ref="future", ended_minutes_ago=-10)

        refs = {c.source_ref for c in await _detect([_event(ref="done"), running])}

        assert "future" not in refs

    async def test_a_follower_that_starts_after_now_still_breaks_the_block(self) -> None:
        """The whole point: the sweep runs BETWEEN two meetings of one block."""
        finished = _event(ref="a", ended_minutes_ago=0)
        # Starts five minutes from now — inside the gap, outside the old window.
        gap = settings.moments_event_chain_gap_minutes
        follower = _event(ref="b", ended_minutes_ago=-(5 + 60), duration=60)

        refs = {c.source_ref for c in await _detect([finished, follower])}

        assert gap >= 5, "this case needs the follower inside the configured gap"
        assert refs == set()


class TestDecliningAfterTheMomentWasFiled:
    """A meeting one declined is not a meeting one had.

    Detection already refuses a declined event. Revalidation did not — although
    its own docstring promised it — so a person who declined between the filing
    and the serve was still asked how it went. The window between the two is
    minutes to hours by design, which is exactly long enough for an answer to
    change.

    One predicate answers it, in `calendar_reading`: the scorer used to carry a
    second copy of the same expression, and two readings of « did they say they
    would not be there » is one too many.
    """

    @staticmethod
    async def _revalidate(event: dict[str, Any] | None) -> Any:
        from contextlib import asynccontextmanager

        client = MagicMock()
        client.get_event = AsyncMock(return_value=event)
        client.close = AsyncMock()

        @asynccontextmanager
        async def _open(_db: Any, _user_id: Any):
            yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.open_active_calendar", new=_open),
        ):
            return await event_followup.revalidate(_user(), "evt-1", {"title": "Point budget"})

    async def test_a_meeting_declined_since_is_no_longer_valid(self) -> None:
        declined = _event(anchor=datetime.now(UTC))
        declined["attendees"] = [
            {"email": ME, "responseStatus": "declined"},
            {"email": "g1@example.com", "displayName": "Guest1"},
        ]

        assert (await self._revalidate(declined)).still_valid is False

    async def test_googles_own_self_marker_is_read_too(self) -> None:
        """An address can be an alias; `self: true` is the provider's own word."""
        declined = _event(anchor=datetime.now(UTC))
        declined["attendees"] = [
            {"email": "alias@example.com", "self": True, "responseStatus": "declined"},
            {"email": "g1@example.com", "displayName": "Guest1"},
        ]

        assert (await self._revalidate(declined)).still_valid is False

    async def test_somebody_else_declining_changes_nothing(self) -> None:
        """They were there; the meeting happened."""
        event = _event(anchor=datetime.now(UTC))
        event["attendees"] = [
            {"email": ME, "responseStatus": "accepted"},
            {"email": "g1@example.com", "displayName": "Guest1", "responseStatus": "declined"},
        ]

        assert (await self._revalidate(event)).still_valid is True

    async def test_an_accepted_meeting_is_still_valid(self) -> None:
        assert (await self._revalidate(_event(anchor=datetime.now(UTC)))).still_valid is True


class TestOneReadingOfDeclined:
    """The scorer and the revalidation must not drift apart."""

    def test_the_scorer_uses_the_shared_predicate(self) -> None:
        import inspect

        from src.domains.moments import importance

        source = inspect.getsource(importance._screen_people)
        assert (
            "is_declined_by_self" in source
        ), "the declined rule has one implementation, in calendar_reading"
        assert (
            "responseStatus" not in source
        ), "a second inline copy of the rule is how the two readings drift"
