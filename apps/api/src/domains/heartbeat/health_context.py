"""Health-signals source for the heartbeat context aggregator.

One heartbeat context source, extracted from ``context_aggregator.py`` for the
same reason ``interest_context.py`` was (ADR-135): the aggregator is a frozen
oversized file, so a source that grows moves out rather than pushing the cap.
It also keeps the aggregator free of health-domain vocabulary — it asks for a
payload and never learns what a kind, a spec or a baseline is.

The source **fails open**: a timeout or an error yields ``None`` and the
heartbeat proceeds without health signals. That is deliberate (a degraded
signal must never cost the user their notification) but it is invisible in the
output, so every drop is counted AND timed — the defect this module was
extracted during went unnoticed for a week precisely because failing open was
silent.

Phase: evolution — Health Metrics × Heartbeat
Created: 2026-07-24
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog

from src.core.constants import HEALTH_METRICS_USER_TOGGLE_ATTR
from src.domains.health_metrics.heartbeat_signals import build_heartbeat_health_signals
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_heartbeat import heartbeat_source_dropped_total

logger = structlog.get_logger(__name__)

#: Label value under ``heartbeat_source_dropped_total{source=...}``.
HEALTH_SIGNALS_SOURCE = "health_signals"


async def fetch_health_signals(
    user_id: UUID,
    user: Any,
    settings: Any,
) -> dict[str, Any] | None:
    """Fetch the Health Metrics signals block when the user has opted in.

    Gated by two flags:

    - ``settings.health_metrics_enabled`` (global feature).
    - ``user.health_metrics_agents_enabled`` (per-user opt-in).

    Wrapped in a wall-clock budget. That budget bounds the coroutine's share of
    an event loop it contends for with the eleven other fetchers of
    ``ContextAggregator.aggregate`` — it is **not** a database timeout, and
    reading it as one is what let a nominal-cost regression hide: the builder
    used to ship ~30 000 raw rows per tick, whose decode alone spent most of the
    budget while PostgreSQL answered in milliseconds. It is now an anomaly
    guard, two orders of magnitude above the nominal cost.

    Args:
        user_id: Owner user UUID.
        user: User ORM model (carries the per-user opt-in flag).
        settings: Application settings (feature flag + budget).

    Returns:
        A dict ready to attach to ``HeartbeatContext.health_signals``, or
        ``None`` when disabled, empty, timed out, or failed.
    """
    if not getattr(settings, "health_metrics_enabled", False):
        return None
    if not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
        return None

    budget_seconds: float = settings.health_metrics_heartbeat_fetch_timeout_seconds
    started = perf_counter()
    try:
        async with asyncio.timeout(budget_seconds):
            async with get_db_context() as db:
                signals = await build_heartbeat_health_signals(db, user_id)
    except TimeoutError:
        heartbeat_source_dropped_total.labels(source=HEALTH_SIGNALS_SOURCE, reason="timeout").inc()
        logger.warning(
            "heartbeat_health_signals_timeout",
            user_id=str(user_id),
            duration_ms=_elapsed_ms(started),
            budget_ms=round(budget_seconds * 1000, 1),
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive
        heartbeat_source_dropped_total.labels(source=HEALTH_SIGNALS_SOURCE, reason="error").inc()
        logger.warning(
            "heartbeat_health_signals_failed",
            user_id=str(user_id),
            duration_ms=_elapsed_ms(started),
            error=str(exc),
        )
        return None

    logger.debug(
        "heartbeat_health_signals_fetched",
        user_id=str(user_id),
        duration_ms=_elapsed_ms(started),
        budget_ms=round(budget_seconds * 1000, 1),
        has_signals=signals is not None,
    )
    return signals


def _elapsed_ms(started: float) -> float:
    """Milliseconds since ``started``, rounded for log readability."""
    return round((perf_counter() - started) * 1000, 1)
