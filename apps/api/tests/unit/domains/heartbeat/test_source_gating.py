"""A refused source is never fetched.

Not merely dropped from the prompt: the fetch itself does not happen, so a
silenced source stops costing an API call too. The oracle is which fetchers
ran, not which fields the context ended up with — a source that is fetched and
then discarded would still hit the connector, still spend quota, and still be
visible in the provider's audit log.

The second-pass sources (journals, memories, departure) live outside the
parallel gather and are gated separately in the aggregator; they are covered
here for exactly that reason.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.heartbeat.context_aggregator import ContextAggregator

pytestmark = pytest.mark.unit


def _user(disabled: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        timezone="Europe/Paris",
        language="fr",
        heartbeat_disabled_sources=disabled,
    )


async def _direct_session(
    _self: object,
    fetch: Callable[..., Awaitable[Any]],
    *args: object,
    **kwargs: object,
) -> Any:
    """Stand-in for `_with_fresh_session`: no DB, the fetcher runs as-is.

    Patched onto the CLASS, so it receives `self` first like any bound method.
    The real one passes a session as the fetcher's first argument; the stubs
    here accept anything, so it is simply omitted.
    """
    return await fetch(*args, **kwargs)


async def _run(disabled: list[str] | None) -> set[str]:
    """Aggregate with every fetcher stubbed; return the ones that ran."""
    called: set[str] = set()

    def _spy(name: str):
        async def _fetch(*_args: object, **_kwargs: object) -> None:
            called.add(name)
            return None

        return _fetch

    aggregator = ContextAggregator(MagicMock())
    user = _user(disabled)

    with (
        patch.object(ContextAggregator, "_fetch_calendar", new=_spy("calendar")),
        patch.object(ContextAggregator, "_fetch_tasks", new=_spy("tasks")),
        patch.object(ContextAggregator, "_fetch_emails", new=_spy("emails")),
        patch.object(ContextAggregator, "_fetch_weather_with_changes", new=_spy("weather")),
        patch.object(ContextAggregator, "_fetch_interests", new=_spy("interests")),
        patch.object(ContextAggregator, "_fetch_memories", new=_spy("memories")),
        patch.object(ContextAggregator, "_fetch_journals", new=_spy("journals")),
        patch.object(ContextAggregator, "_fetch_birthdays", new=_spy("birthdays")),
        patch.object(ContextAggregator, "_fetch_activity", new=_spy("activity")),
        patch.object(ContextAggregator, "_fetch_recent_heartbeats", new=_spy("recent_heartbeats")),
        patch.object(
            ContextAggregator, "_fetch_recent_interest_notifications", new=_spy("recent_interests")
        ),
        patch.object(
            ContextAggregator, "_fetch_recent_other_notifications", new=_spy("recent_other")
        ),
        patch(
            "src.domains.heartbeat.context_aggregator.fetch_health_signals",
            new=_spy("health_signals"),
        ),
        patch(
            "src.domains.heartbeat.context_aggregator.fetch_open_loops_context",
            new=_spy("open_loops"),
        ),
        patch(
            "src.domains.heartbeat.context_aggregator.fetch_departure_advice",
            new=_spy("departure"),
        ),
        # `_with_fresh_session` wraps most fetchers with a DB session; here it
        # calls the fetcher directly (the session plumbing is not under test).
        patch.object(ContextAggregator, "_with_fresh_session", new=_direct_session),
    ):
        await aggregator.aggregate(user.id, user)

    return called


class TestGating:
    async def test_every_source_runs_when_nothing_is_refused(self) -> None:
        called = await _run(None)

        for expected in ("calendar", "emails", "tasks", "weather", "interests", "birthdays"):
            assert expected in called, expected
        # Second-pass sources too.
        for expected in ("journals", "memories", "departure"):
            assert expected in called, expected

    async def test_a_refused_source_is_not_even_fetched(self) -> None:
        called = await _run(["emails", "weather"])

        assert "emails" not in called
        assert "weather" not in called
        assert "calendar" in called

    async def test_refusing_a_second_pass_source_skips_its_fetch_too(self) -> None:
        """Journals, memories and departure bypass the parallel gather."""
        called = await _run(["journals", "memories", "departure"])

        assert "journals" not in called
        assert "memories" not in called
        assert "departure" not in called

    async def test_internal_context_is_never_gated(self) -> None:
        """Anti-redundancy windows are not sources — silencing them would make
        the assistant repeat itself rather than interrupt less."""
        called = await _run(sorted({"calendar", "emails", "tasks", "weather", "interests"}))

        assert "recent_heartbeats" in called
        assert "recent_interests" in called
        assert "recent_other" in called
        assert "activity" in called

    async def test_refusing_everything_does_not_break_the_cycle(self) -> None:
        from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_KEYS

        called = await _run(sorted(HEARTBEAT_SOURCE_KEYS))

        assert called.isdisjoint(HEARTBEAT_SOURCE_KEYS)
