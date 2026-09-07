"""The second-pass query names what the cycle is actually about.

Extracted from the aggregator on 2026-09-07 to keep that module under its
shrink-only size cap — and shipped with no test at all, which is how an
extraction turns into a blind spot: the code left a covered module and landed
in an uncovered one without a single line changing.

The query is DYNAMIC on purpose (P8, ADR-135). The static one it replaced
anchored the same journals and the same memories cycle after cycle, so what
matters here is that each source actually reaches the query — a silently
dropped branch would restore the old behaviour with nothing to show for it.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.heartbeat.second_pass_query import build_second_pass_query

pytestmark = pytest.mark.unit


class _Context:
    """The five fields the builder reads, and nothing else."""

    def __init__(self, **fields: Any) -> None:
        self.calendar_events: list[dict] = fields.get("calendar_events") or []
        self.weather_current: dict | None = fields.get("weather_current")
        self.trending_interests: list[dict] = fields.get("trending_interests") or []
        self.pending_tasks: list[dict] = fields.get("pending_tasks") or []
        self.unread_emails: list[dict] = fields.get("unread_emails") or []


def _build(**fields: Any) -> str:
    return build_second_pass_query(_Context(**fields))  # type: ignore[arg-type]


class TestEachSourceReachesTheQuery:
    """A branch that stops contributing restores the static query in silence."""

    def test_events_are_named(self) -> None:
        query = _build(calendar_events=[{"summary": "Dentist"}, {"summary": "Standup"}])
        assert "upcoming events: Dentist, Standup" in query

    def test_weather_is_named(self) -> None:
        assert "weather: light rain" in _build(weather_current={"description": "light rain"})

    def test_interests_are_named(self) -> None:
        assert "interests: rugby, jazz" in _build(
            trending_interests=[{"topic": "rugby"}, {"topic": "jazz"}]
        )

    def test_tasks_are_named(self) -> None:
        assert "tasks: Call the plumber" in _build(pending_tasks=[{"title": "Call the plumber"}])

    def test_emails_are_named(self) -> None:
        assert "emails: Invoice #12" in _build(unread_emails=[{"subject": "Invoice #12"}])

    def test_every_source_contributes_at_once(self) -> None:
        query = _build(
            calendar_events=[{"summary": "Dentist"}],
            weather_current={"description": "sunny"},
            trending_interests=[{"topic": "rugby"}],
            pending_tasks=[{"title": "Plumber"}],
            unread_emails=[{"subject": "Invoice"}],
        )
        for expected in ("upcoming events:", "weather:", "interests:", "tasks:", "emails:"):
            assert expected in query


class TestTheCapsAreTheOnesDeclared:
    """A query that grows with the mailbox stops selecting and starts diluting."""

    def test_at_most_three_events(self) -> None:
        query = _build(calendar_events=[{"summary": f"E{i}"} for i in range(6)])
        assert "E0, E1, E2" in query
        assert "E3" not in query

    def test_at_most_three_interests(self) -> None:
        query = _build(trending_interests=[{"topic": f"T{i}"} for i in range(5)])
        assert "T3" not in query

    def test_at_most_three_tasks(self) -> None:
        query = _build(pending_tasks=[{"title": f"K{i}"} for i in range(5)])
        assert "K3" not in query

    def test_at_most_two_emails(self) -> None:
        """Two, not three — the one cap that differs, and the easiest to lose."""
        query = _build(unread_emails=[{"subject": f"M{i}"} for i in range(4)])
        assert "M0, M1" in query
        assert "M2" not in query


class TestWhenThereIsNothingToSayItSaysSo:
    """An empty query embeds to noise and selects at random."""

    def test_an_empty_context_falls_back_to_the_standing_query(self) -> None:
        assert _build() == "user preferences observations patterns priorities"

    def test_a_source_present_but_empty_is_not_a_source(self) -> None:
        assert _build(calendar_events=[], unread_emails=[]) == (
            "user preferences observations patterns priorities"
        )

    def test_a_missing_field_never_raises(self) -> None:
        """The fetchers return dicts a provider shaped; keys go missing."""
        query = _build(
            calendar_events=[{}],
            weather_current={},
            trending_interests=[{}],
            pending_tasks=[{}],
            unread_emails=[{}],
        )
        assert query
        assert "upcoming events: " in query
