"""Consent-fenced native chart aggregates; bounded UTC windows, no future claims."""

from datetime import timedelta

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.read_budget import mark_read_opened
from src.domains.health_metrics.chart_read import read_chart_statistics
from src.domains.health_metrics.discussion_projection import daily_evidence
from src.domains.shared.discussion_sources import (
    RESEARCH_HISTORY_DAYS_MAX,
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

_MAXIMUM_DAILY_BUCKETS = RESEARCH_HISTORY_DAYS_MAX + 2


def _page_result(
    items: tuple[DiscussionEvidence, ...], request: SourceReadRequest
) -> SourceSnapshot:
    revision = semantic_version(
        (
            str(request.owner_id),
            request.window_start.isoformat(),
            request.window_end.isoformat(),
            *(item.version for item in items),
        )
    )
    offset = 0
    if request.cursor is not None:
        previous, separator, raw_offset = request.cursor.partition(":")
        if not separator or previous != revision or not raw_offset.isdecimal():
            raise ResourceConflictError(
                "health context cursor", detail={"error_code": "STALE_STATE"}
            )
        offset = int(raw_offset)
        if offset >= len(items):
            raise ResourceConflictError(
                "health context cursor", detail={"error_code": "STALE_STATE"}
            )
    page = items[offset : offset + request.item_limit]
    more = offset + len(page) < len(items)
    return source_snapshot(
        request,
        status="truncated" if more else ("ok" if page else "empty"),
        coverage_kind="signal",
        items=page,
        total=len(items),
        complete=not (more or request.cursor),
        cursor=f"{revision}:{offset + len(page)}" if more else None,
        revision=revision,
    )


class HealthDiscussionSource:
    """The person's health metrics, behind the instance flag and two consents."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of past daily health aggregates in the window (recent or history).

        Args:
            request: The bounded read.

        Returns:
            The page; closed when health metrics are off on the instance, the source or the health
            topic is not consented, the person did not let agents read their metrics, or the
            operation or window is not one the source serves.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceConflictError: The cursor belongs to an older page (STALE_STATE).
        """
        if request.request.source != SourceKey.HEALTH:
            raise ValueError("health source mismatch")
        if not settings.health_metrics_enabled:
            return closed_source(request, disabled=True, reason="feature")
        if (
            SourceKey.HEALTH not in request.allowed_sources
            or "health" not in request.sensitive_topics
        ):
            return closed_source(request, disabled=True, reason="consent")
        if request.request.operation not in {"recent", "history"}:
            return closed_source(request, disabled=False, reason="malformed")
        end = min(request.window_end, request.now)
        if request.window_start >= end:
            return closed_source(request, disabled=False, reason="expired")
        scope = request.model_copy(update={"window_end": end})
        if end - scope.window_start > timedelta(days=RESEARCH_HISTORY_DAYS_MAX):
            return closed_source(request, disabled=False, reason="budget")
        async with get_db_context() as db:
            enabled = await db.scalar(
                select(User.health_metrics_agents_enabled)
                .where(
                    User.id == scope.owner_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
                .with_for_update(read=True)
            )
            if not enabled:
                return closed_source(scope, disabled=True, reason="consent")
            mark_read_opened(scope.owner_id)
            chart = await read_chart_statistics(
                db,
                scope.owner_id,
                period="day",
                from_ts=scope.window_start,
                to_ts=scope.window_end,
                maximum_buckets=_MAXIMUM_DAILY_BUCKETS,
            )
        try:
            items = daily_evidence(chart, scope)
        except ValueError:
            return closed_source(scope, disabled=False, reason="budget")
        return _page_result(items, scope)
