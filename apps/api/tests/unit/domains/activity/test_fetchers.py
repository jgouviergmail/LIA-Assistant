"""Activity timeline fetchers and row→event mappers (Lot 1-A1).

Mappers are pure (SimpleNamespace rows in, ActivityEvent out). Fetchers are
tested with a patched ``get_db_context`` and repository (briefing style).
Reminders are deliberately ABSENT: delivered reminders leave no persisted
row (ephemeral, deleted after firing) — no trace, no claim (ADR-185).
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.activity.constants import (
    ACTIVITY_KIND_HABIT_DETECTED,
    ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
    ACTIVITY_KIND_INTEREST_NOTIFICATION,
    ACTIVITY_KIND_JOURNAL_ENTRY,
    ACTIVITY_KIND_OPEN_LOOP_CLOSED,
    ACTIVITY_KIND_OPEN_LOOP_CREATED,
    ACTIVITY_KIND_SCHEDULED_ACTION_RUN,
    ALL_ACTIVITY_KINDS,
)
from src.domains.activity.fetchers import (
    ALL_SOURCE_FETCHERS,
    fetch_habits,
    fetch_heartbeat_notifications,
    fetch_open_loops,
    map_habit,
    map_heartbeat_notification,
    map_interest_notification,
    map_journal_entry,
    map_open_loop,
    map_scheduled_action,
)

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=30)


def _db_ctx():
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        yield MagicMock()

    return _ctx


# =============================================================================
# Pure mappers
# =============================================================================


@pytest.mark.unit
class TestMappers:
    def test_heartbeat_notification_maps_content_and_priority(self):
        row_id = uuid4()
        row = SimpleNamespace(
            id=row_id,
            content="Il pleut à 14h, pense au parapluie",
            priority="medium",
            created_at=NOW,
        )

        event = map_heartbeat_notification(row)

        assert event.kind == ACTIVITY_KIND_HEARTBEAT_NOTIFICATION
        assert event.ref_id == str(row_id)
        assert event.text == "Il pleut à 14h, pense au parapluie"
        assert event.status == "medium"
        assert event.occurred_at == NOW

    def test_interest_notification_tolerates_null_content(self):
        # Rows predating 2026-08-03 legitimately have content=None: the event
        # renders without its paragraph rather than inventing one.
        row = SimpleNamespace(id=uuid4(), content=None, created_at=NOW)

        event = map_interest_notification(row)

        assert event.kind == ACTIVITY_KIND_INTEREST_NOTIFICATION
        assert event.text is None
        assert event.status is None

    def test_journal_entry_maps_title_and_source(self):
        row = SimpleNamespace(
            id=uuid4(),
            title="Semaine chargée au travail",
            source="consolidation",
            created_at=NOW,
        )

        event = map_journal_entry(row)

        assert event.kind == ACTIVITY_KIND_JOURNAL_ENTRY
        assert event.text == "Semaine chargée au travail"
        assert event.status == "consolidation"

    def test_habit_maps_key_and_status(self):
        row = SimpleNamespace(id=uuid4(), key="evening_review", status="active", created_at=NOW)

        event = map_habit(row)

        assert event.kind == ACTIVITY_KIND_HABIT_DETECTED
        assert event.text == "evening_review"
        assert event.status == "active"

    def test_scheduled_action_uses_last_executed_at(self):
        executed = NOW - timedelta(hours=2)
        row = SimpleNamespace(id=uuid4(), title="Revue de presse IA", last_executed_at=executed)

        event = map_scheduled_action(row)

        assert event.kind == ACTIVITY_KIND_SCHEDULED_ACTION_RUN
        assert event.text == "Revue de presse IA"
        assert event.occurred_at == executed


@pytest.mark.unit
class TestMapOpenLoop:
    def _loop(self, *, created_at, updated_at, status="open", closed_reason=None):
        return SimpleNamespace(
            id=uuid4(),
            subject="rappeler le plombier",
            status=status,
            closed_reason=closed_reason,
            created_at=created_at,
            updated_at=updated_at,
        )

    def test_open_loop_created_in_window_yields_created_event(self):
        loop = self._loop(created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(days=1))

        events = map_open_loop(loop, since=SINCE)

        assert [e.kind for e in events] == [ACTIVITY_KIND_OPEN_LOOP_CREATED]
        assert events[0].text == "rappeler le plombier"

    def test_closed_loop_in_window_yields_both_events(self):
        loop = self._loop(
            created_at=NOW - timedelta(days=2),
            updated_at=NOW - timedelta(days=1),
            status="closed",
            closed_reason="done",
        )

        events = map_open_loop(loop, since=SINCE)

        kinds = [e.kind for e in events]
        assert kinds == [ACTIVITY_KIND_OPEN_LOOP_CREATED, ACTIVITY_KIND_OPEN_LOOP_CLOSED]
        closed = events[1]
        assert closed.status == "done"
        assert closed.occurred_at == loop.updated_at

    def test_loop_created_before_window_closed_inside_yields_only_closed(self):
        loop = self._loop(
            created_at=SINCE - timedelta(days=5),
            updated_at=NOW - timedelta(days=1),
            status="expired",
        )

        events = map_open_loop(loop, since=SINCE)

        assert [e.kind for e in events] == [ACTIVITY_KIND_OPEN_LOOP_CLOSED]
        # Expired loops carry their lifecycle end honestly.
        assert events[0].status == "expired"

    def test_open_loop_created_before_window_yields_nothing(self):
        loop = self._loop(
            created_at=SINCE - timedelta(days=5), updated_at=SINCE - timedelta(days=5)
        )

        assert map_open_loop(loop, since=SINCE) == []


# =============================================================================
# Fetchers (patched repo + session)
# =============================================================================


@pytest.mark.unit
class TestFetchers:
    async def test_heartbeat_fetcher_returns_bundle_with_exact_total(self):
        rows = [
            SimpleNamespace(id=uuid4(), content=f"notif {i}", priority="low", created_at=NOW)
            for i in range(3)
        ]
        repo = MagicMock()
        repo.heartbeat_notifications_since = AsyncMock(return_value=(rows, 12))

        with (
            patch("src.domains.activity.fetchers.get_db_context", new=_db_ctx()),
            patch("src.domains.activity.fetchers.ActivityReadRepository", return_value=repo),
        ):
            bundles = await fetch_heartbeat_notifications(user_id=uuid4(), since=SINCE, cap=10)

        assert len(bundles) == 1
        bundle = bundles[0]
        assert bundle.kind == ACTIVITY_KIND_HEARTBEAT_NOTIFICATION
        assert len(bundle.events) == 3
        assert bundle.total == 12
        # 12 rows exist, only 3 fetched under cap 10? No: total > len(rows)
        # means the window holds more than what was fetched — stated, not silent.
        assert bundle.truncated is True

    async def test_fetcher_not_truncated_when_all_rows_fetched(self):
        rows = [SimpleNamespace(id=uuid4(), key="k", status="active", created_at=NOW)]
        repo = MagicMock()
        repo.habits_since = AsyncMock(return_value=(rows, 1))

        with (
            patch("src.domains.activity.fetchers.get_db_context", new=_db_ctx()),
            patch("src.domains.activity.fetchers.ActivityReadRepository", return_value=repo),
        ):
            bundles = await fetch_habits(user_id=uuid4(), since=SINCE, cap=10)

        assert bundles[0].truncated is False

    async def test_open_loop_fetcher_returns_two_bundles_with_own_totals(self):
        loops = [
            SimpleNamespace(
                id=uuid4(),
                subject="s1",
                status="closed",
                closed_reason="done",
                created_at=NOW - timedelta(days=1),
                updated_at=NOW,
            )
        ]
        repo = MagicMock()
        repo.open_loops_since = AsyncMock(return_value=(loops, 4, 2))

        with (
            patch("src.domains.activity.fetchers.get_db_context", new=_db_ctx()),
            patch("src.domains.activity.fetchers.ActivityReadRepository", return_value=repo),
        ):
            bundles = await fetch_open_loops(user_id=uuid4(), since=SINCE, cap=10)

        by_kind = {b.kind: b for b in bundles}
        assert set(by_kind) == {
            ACTIVITY_KIND_OPEN_LOOP_CREATED,
            ACTIVITY_KIND_OPEN_LOOP_CLOSED,
        }
        assert by_kind[ACTIVITY_KIND_OPEN_LOOP_CREATED].total == 4
        assert by_kind[ACTIVITY_KIND_OPEN_LOOP_CLOSED].total == 2
        # One row produced one created + one closed event.
        assert len(by_kind[ACTIVITY_KIND_OPEN_LOOP_CREATED].events) == 1
        assert len(by_kind[ACTIVITY_KIND_OPEN_LOOP_CLOSED].events) == 1


@pytest.mark.unit
class TestSourceRegistry:
    def test_every_kind_is_produced_by_exactly_one_fetcher(self):
        # Registry completeness (ADR-085 doctrine, test-time variant): every
        # declared kind must be covered by the fetcher table, no orphans.
        covered: set[str] = set()
        for fetcher in ALL_SOURCE_FETCHERS:
            for kind in fetcher.kinds:
                assert kind not in covered, f"kind {kind} produced twice"
                covered.add(kind)
        assert covered == set(ALL_ACTIVITY_KINDS)
