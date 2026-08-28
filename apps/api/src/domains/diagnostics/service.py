"""Diagnostics read services (briefing pattern: compose, cache, split).

``build_overview`` is the ONE implementation of the platform-health view,
consumed verbatim by the admin REST endpoint and the platform_health chat
tool (factorisation contract, enforced by test_admin_router). The composed
view is Redis-cached for a short TTL: the settings page polls it, and two
admins must not multiply telemetry reads.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_OVERVIEW_CACHE
from src.domains.diagnostics.advisor import get_active_degradations
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.telemetry.alertmanager import AlertmanagerClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Cap on alerts embedded in the overview payload (exact total travels along).
_MAX_EMBEDDED_ALERTS = 50


async def build_overview(db: AsyncSession) -> dict[str, Any]:
    """Compose the platform-health overview (uncached).

    Args:
        db: Caller's session.

    Returns:
        JSON-serializable overview: latest snapshot, firing alerts, exact
        open-incident count, current degradations. Unreachable sources are
        reported as 'unavailable' — never as an exception.
    """
    repo = DiagnosticsRepository(db)
    snapshot = await repo.latest_snapshot()
    _, open_incidents = await repo.list_incidents(status="open", page=1, page_size=1)

    alerts_result = await AlertmanagerClient(
        base_url=settings.diagnostics_alertmanager_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    ).active_alerts()
    degradations = await get_active_degradations()

    overview: dict[str, Any] = {
        "snapshot_available": snapshot is not None,
        "open_incidents": open_incidents,
        "alertmanager": alerts_result.status,
        "active_alerts": [
            {
                "name": alert.name,
                "severity": alert.severity,
                "component": alert.component,
                "summary": alert.summary,
            }
            for alert in alerts_result.alerts[:_MAX_EMBEDDED_ALERTS]
        ],
        "total_active_alerts": len(alerts_result.alerts),
        "degradations": [
            {
                "capability": d.capability,
                "status": d.status,
                "reason": d.reason,
                "alternative": d.alternative,
            }
            for d in degradations
        ],
    }
    if snapshot is not None:
        overview["overall"] = snapshot.overall
        overview["taken_at"] = snapshot.taken_at.isoformat()
        overview["checks"] = snapshot.results
    return overview


async def build_overview_cached(db: AsyncSession) -> dict[str, Any]:
    """The overview through a short-TTL Redis cache (fail-open to uncached).

    Args:
        db: Caller's session (used only on a cache miss).

    Returns:
        The overview dict (see ``build_overview``).
    """
    try:
        redis = await get_redis_cache()
        cached = await redis.get(REDIS_KEY_DIAGNOSTICS_OVERVIEW_CACHE)
        if cached is not None:
            parsed = json.loads(cached)
            if isinstance(parsed, dict):
                return parsed
    except Exception as exc:
        logger.debug("diagnostics_overview_cache_read_failed", error=str(exc))

    overview = await build_overview(db)
    try:
        redis = await get_redis_cache()
        await redis.set(
            REDIS_KEY_DIAGNOSTICS_OVERVIEW_CACHE,
            json.dumps(overview),
            ex=settings.diagnostics_advisor_cache_ttl_seconds,
        )
    except Exception as exc:
        logger.debug("diagnostics_overview_cache_write_failed", error=str(exc))
    return overview
