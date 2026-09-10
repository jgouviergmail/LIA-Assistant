"""Where a source's result lands on the context, and whether it counts.

Captured BEFORE the extraction of `_apply_source_result` (ADR-276 lot 6), the
same way ADR-269 froze the 360° payload before moving it: the chain of fourteen
`elif` branches was a correspondence table written in control flow, and a table
is only safe to substitute for branches once the branches are pinned.

Three shapes hide in that chain, and only one of them is a plain assignment:

- ten sources set ONE field and ANNOUNCE themselves in ``available_sources``;
- the three anti-redundancy windows set one field and announce NOTHING — they
  say what LIA already sent, not what it may say;
- ``activity`` unpacks a pair, and ``weather`` unpacks four values under three
  separate conditions.

The last two stay explicit on purpose. A table that lied about one entry would
be worse than the branches it replaced.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.heartbeat import context_aggregator as aggregator_module
from src.domains.heartbeat.context_aggregator import ContextAggregator
from src.domains.heartbeat.schemas import HeartbeatContext

pytestmark = pytest.mark.unit


def _aggregator() -> ContextAggregator:
    return ContextAggregator(MagicMock())


def _changed(context: HeartbeatContext) -> dict[str, Any]:
    """Every field of the context that differs from an untouched one."""
    fresh = HeartbeatContext()
    return {
        field.name: getattr(context, field.name)
        for field in fields(HeartbeatContext)
        if getattr(context, field.name) != getattr(fresh, field.name)
    }


#: name -> (result handed to the dispatcher, fields it must change)
SIMPLE_SOURCES: tuple[tuple[str, str], ...] = (
    ("calendar", "calendar_events"),
    ("tasks", "pending_tasks"),
    ("emails", "unread_emails"),
    ("interests", "trending_interests"),
    ("memories", "user_memories"),
    ("journals", "journal_entries"),
    ("health_signals", "health_signals"),
    ("birthdays", "upcoming_birthdays"),
    ("open_loops", "open_loops"),
    ("habits", "habits"),
)

#: The windows that read LIA's OWN past notifications: they never announce.
SILENT_SOURCES: tuple[tuple[str, str], ...] = (
    ("recent_heartbeats", "recent_heartbeats"),
    ("recent_interests", "recent_interest_notifications"),
    ("recent_other", "recent_other_notifications"),
)


class TestASourceThatAnnouncesItself:
    @pytest.mark.parametrize(("name", "field"), SIMPLE_SOURCES)
    def test_it_lands_on_its_field_and_joins_the_available_list(
        self, name: str, field: str
    ) -> None:
        context = HeartbeatContext()
        payload = [{"probe": name}]

        _aggregator()._apply_source_result(context, name, payload)

        assert _changed(context) == {field: payload, "available_sources": [name]}

    @pytest.mark.parametrize(("name", "field"), SIMPLE_SOURCES)
    def test_an_empty_result_changes_nothing(self, name: str, field: str) -> None:
        """An empty list is « the source ran and found nothing », never « the
        source is available »: announcing it would put an empty section in
        front of the decision."""
        context = HeartbeatContext()

        _aggregator()._apply_source_result(context, name, [])

        assert _changed(context) == {}


class TestAWindowThatSaysWhatWasAlreadySent:
    @pytest.mark.parametrize(("name", "field"), SILENT_SOURCES)
    def test_it_lands_without_announcing_itself(self, name: str, field: str) -> None:
        context = HeartbeatContext()
        payload = [{"probe": name}]

        _aggregator()._apply_source_result(context, name, payload)

        assert _changed(context) == {field: payload}
        assert context.available_sources == []


class TestTheTwoShapesThatAreNotAssignments:
    def test_activity_unpacks_a_pair(self) -> None:
        context = HeartbeatContext()
        moment = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

        _aggregator()._apply_source_result(context, "activity", (moment, 4.5))

        assert _changed(context) == {
            "last_interaction_at": moment,
            "hours_since_last_interaction": 4.5,
        }
        # Never announced: how long ago somebody spoke is not a source of news.
        assert context.available_sources == []

    def test_weather_announces_only_on_the_CURRENT_reading(self) -> None:
        """The four values are independent: a forecast change with no current
        reading must not make « weather » an available source."""
        context = HeartbeatContext()

        _aggregator()._apply_source_result(context, "weather", (None, ["a change"], "home", "Lyon"))

        assert context.available_sources == []
        assert context.weather_changes == ["a change"]
        assert context.weather_location_source == "home"
        assert context.weather_location_city == "Lyon"

    def test_weather_with_a_current_reading_announces_once(self) -> None:
        context = HeartbeatContext()

        _aggregator()._apply_source_result(context, "weather", ({"t": 21}, None, None, None))

        assert context.available_sources == ["weather"]
        assert context.weather_current == {"t": 21}
        assert context.weather_changes is None


class TestAnUnknownName:
    def test_it_places_nothing_and_says_so(self) -> None:
        """Unreachable by construction — ``assert_placements_complete`` refuses
        the boot when a gateable source has nowhere to land — but reached at
        all it must be LOUD, never silent. The silent fallback is what ADR-085
        forbids, and the chain this table replaced had exactly one."""
        context = HeartbeatContext()

        with patch.object(aggregator_module, "logger") as log:
            _aggregator()._apply_source_result(context, "no_such_source", [{"x": 1}])

        assert _changed(context) == {}
        log.warning.assert_called_once()
        assert log.warning.call_args.args[0] == "heartbeat_source_unplaced"
