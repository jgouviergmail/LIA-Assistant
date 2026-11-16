"""The one start-order key the calendar clients sort a window by (ADR-185 amendment).

Proven away from UTC (ADR-380): two offsets spelled differently sort wrong as text,
and Graph spells a wall time with its zone beside it rather than in it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domains.connectors.clients.event_order import soonest_first, start_instant

pytestmark = pytest.mark.unit


def _event(event_id: str, **start: str) -> dict[str, object]:
    return {"id": event_id, "start": start}


class TestStartInstant:
    def test_offsets_are_compared_as_instants_not_as_text(self) -> None:
        # 10:00 in Paris (UTC+1 in November) is 09:00 UTC: before 09:30 UTC.
        paris = _event("paris", dateTime="2026-11-15T10:00:00+01:00")
        london = _event("london", dateTime="2026-11-15T09:30:00+00:00")
        assert [e["id"] for e in soonest_first([london, paris])] == ["paris", "london"]

    def test_a_bare_wall_time_is_read_in_the_zone_beside_it(self) -> None:
        graph = _event("graph", dateTime="2026-11-15T10:00:00.0000000", timeZone="Europe/Paris")
        assert start_instant(graph) == datetime(2026, 11, 15, 9, 0, tzinfo=UTC)

    def test_a_zone_it_cannot_read_falls_back_to_utc(self) -> None:
        windows = _event("w", dateTime="2026-11-15T10:00:00", timeZone="Romance Standard Time")
        assert start_instant(windows) == datetime(2026, 11, 15, 10, 0, tzinfo=UTC)

    def test_an_all_day_event_starts_at_its_day_s_midnight_utc(self) -> None:
        assert start_instant(_event("d", date="2026-11-15")) == datetime(2026, 11, 15, tzinfo=UTC)

    def test_an_unreadable_start_sorts_last(self) -> None:
        events = [_event("bad", dateTime="soon"), _event("ok", dateTime="2026-11-15T10:00:00Z")]
        assert [e["id"] for e in soonest_first(events)] == ["ok", "bad"]
