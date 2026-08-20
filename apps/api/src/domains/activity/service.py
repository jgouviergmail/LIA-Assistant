"""ActivityService — parallel source aggregation for the timeline (Lot 1-A1).

Pure read orchestration (briefing doctrine): sources run in parallel via
``asyncio.gather``, each fetcher owning its DB session. A failed source is
reported in ``failed_kinds`` and contributes NO total — partial data is
stated, never silently completed (ADR-185 honesty doctrine).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.activity.fetchers import ALL_SOURCE_FETCHERS
from src.domains.activity.schemas import (
    ActivityEvent,
    ActivityKindTotal,
    ActivityTimelineResponse,
)
from src.domains.activity.timeline import merge_timeline

logger = structlog.get_logger(__name__)


class ActivityService:
    """Read-only aggregation of the user's proactive activity."""

    def __init__(self, user_id: UUID) -> None:
        """Bind the service to the authenticated owner."""
        self._user_id = user_id

    async def build_timeline(self, *, offset: int, limit: int) -> ActivityTimelineResponse:
        """Fetch all sources in parallel and return one merged page.

        Args:
            offset: Rows to skip (validated upstream by the router).
            limit: Page size (validated upstream by the router).

        Returns:
            The merged page with exact per-kind totals and failed sources.
        """
        window_days = settings.activity_timeline_window_days
        since = datetime.now(UTC) - timedelta(days=window_days)
        cap = settings.activity_timeline_source_cap

        results = await asyncio.gather(
            *(
                source.fetch(user_id=self._user_id, since=since, cap=cap)
                for source in ALL_SOURCE_FETCHERS
            ),
            return_exceptions=True,
        )

        events_by_kind: dict[str, list[ActivityEvent]] = {}
        totals: list[ActivityKindTotal] = []
        failed_kinds: list[str] = []
        for source, result in zip(ALL_SOURCE_FETCHERS, results, strict=True):
            if isinstance(result, BaseException):
                failed_kinds.extend(source.kinds)
                logger.warning(
                    "activity_timeline_source_failed",
                    kinds=list(source.kinds),
                    error=str(result),
                    error_type=type(result).__name__,
                )
                continue
            for bundle in result:
                events_by_kind[bundle.kind] = bundle.events
                totals.append(
                    ActivityKindTotal(
                        kind=bundle.kind, total=bundle.total, truncated=bundle.truncated
                    )
                )

        merged = merge_timeline(events_by_kind, offset=offset, limit=limit)
        logger.info(
            "activity_timeline_built",
            user_id=str(self._user_id),
            window_days=window_days,
            page_events=len(merged.events),
            total_fetched=merged.total_fetched,
            failed_kinds=failed_kinds,
        )
        return ActivityTimelineResponse(
            events=merged.events,
            totals=totals,
            has_more=merged.has_more,
            offset=offset,
            limit=limit,
            window_days=window_days,
            failed_kinds=failed_kinds,
        )
