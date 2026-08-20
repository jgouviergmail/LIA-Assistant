"""ActivityService orchestration (Lot 1-A1): parallel fetch, honest failures.

The service gathers all registered sources in parallel, merges their
events, and reports partial failures explicitly (``failed_kinds``) — a
broken source must neither kill the page nor vanish silently.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.domains.activity.constants import (
    ACTIVITY_KIND_HABIT_DETECTED,
    ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
)
from src.domains.activity.fetchers import KindBundle, TimelineSource
from src.domains.activity.schemas import ActivityEvent
from src.domains.activity.service import ActivityService

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)


def _event(kind: str, ref_id: str, minutes_ago: int) -> ActivityEvent:
    return ActivityEvent(kind=kind, ref_id=ref_id, occurred_at=NOW - timedelta(minutes=minutes_ago))


def _source(kind: str, events: list[ActivityEvent], total: int | None = None) -> TimelineSource:
    async def _fetch(*, user_id, since, cap):
        return [
            KindBundle(
                kind=kind,
                events=events,
                total=total if total is not None else len(events),
                truncated=(total or len(events)) > len(events),
            )
        ]

    return TimelineSource((kind,), _fetch)


def _failing_source(kind: str) -> TimelineSource:
    async def _fetch(*, user_id, since, cap):
        raise RuntimeError("source exploded")

    return TimelineSource((kind,), _fetch)


@pytest.mark.unit
class TestActivityService:
    async def test_merges_sources_and_reports_exact_totals(self):
        sources = (
            _source(
                ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
                [_event(ACTIVITY_KIND_HEARTBEAT_NOTIFICATION, "hb1", 5)],
                total=7,
            ),
            _source(
                ACTIVITY_KIND_HABIT_DETECTED,
                [_event(ACTIVITY_KIND_HABIT_DETECTED, "h1", 2)],
            ),
        )

        with patch("src.domains.activity.service.ALL_SOURCE_FETCHERS", sources):
            response = await ActivityService(uuid4()).build_timeline(offset=0, limit=10)

        assert [e.ref_id for e in response.events] == ["h1", "hb1"]
        totals = {t.kind: t for t in response.totals}
        assert totals[ACTIVITY_KIND_HEARTBEAT_NOTIFICATION].total == 7
        assert totals[ACTIVITY_KIND_HEARTBEAT_NOTIFICATION].truncated is True
        assert totals[ACTIVITY_KIND_HABIT_DETECTED].total == 1
        assert response.failed_kinds == []
        assert response.has_more is False

    async def test_failed_source_is_reported_not_fatal(self):
        sources = (
            _source(
                ACTIVITY_KIND_HABIT_DETECTED,
                [_event(ACTIVITY_KIND_HABIT_DETECTED, "h1", 2)],
            ),
            _failing_source(ACTIVITY_KIND_HEARTBEAT_NOTIFICATION),
        )

        with patch("src.domains.activity.service.ALL_SOURCE_FETCHERS", sources):
            response = await ActivityService(uuid4()).build_timeline(offset=0, limit=10)

        assert [e.ref_id for e in response.events] == ["h1"]
        assert response.failed_kinds == [ACTIVITY_KIND_HEARTBEAT_NOTIFICATION]
        # A failed source contributes NO total: absent, never a fake zero.
        assert ACTIVITY_KIND_HEARTBEAT_NOTIFICATION not in {t.kind for t in response.totals}

    async def test_pagination_flows_through_to_merge(self):
        events = [_event(ACTIVITY_KIND_HABIT_DETECTED, f"h{i}", i) for i in range(1, 5)]
        sources = (_source(ACTIVITY_KIND_HABIT_DETECTED, events),)

        with patch("src.domains.activity.service.ALL_SOURCE_FETCHERS", sources):
            response = await ActivityService(uuid4()).build_timeline(offset=1, limit=2)

        assert [e.ref_id for e in response.events] == ["h2", "h3"]
        assert response.has_more is True
        assert response.offset == 1
        assert response.limit == 2

    async def test_window_days_comes_from_settings(self):
        captured: dict[str, object] = {}

        async def _fetch(*, user_id, since, cap):
            captured["since"] = since
            captured["cap"] = cap
            return [
                KindBundle(kind=ACTIVITY_KIND_HABIT_DETECTED, events=[], total=0, truncated=False)
            ]

        sources = (TimelineSource((ACTIVITY_KIND_HABIT_DETECTED,), _fetch),)

        with patch("src.domains.activity.service.ALL_SOURCE_FETCHERS", sources):
            from src.core.config import settings

            response = await ActivityService(uuid4()).build_timeline(offset=0, limit=10)

            expected_since_floor = datetime.now(UTC) - timedelta(
                days=settings.activity_timeline_window_days
            )
            assert captured["cap"] == settings.activity_timeline_source_cap
            # since ≈ now - window (tolerance for test runtime)
            assert abs((captured["since"] - expected_since_floor).total_seconds()) < 5
            assert response.window_days == settings.activity_timeline_window_days
