"""Helper for tracking Google API calls from clients.

This module provides a simple function to track Google API calls using
the ContextVar pattern. It's designed to be called from anywhere in the
async call stack without explicit tracker parameter passing.

**It fails closed.** A paid call made where no ``TrackingContext`` is ambient
used to be dropped in silence — by design, this docstring said « does nothing
if no tracker active ». That silence was a euro the deployment paid and nobody
filed, on every surface that reaches a Maps Platform client outside a chat
turn (measured 2026-09-19: 3 020 usage rows on dev, not one outside a turn).
Such a call is now counted (``google_api_calls_unaccounted_total``) and named
in the logs; every out-of-turn surface opens its own accounting
(``domains/google_api/spend_roads.py`` declares which), so the counter's
expected value is zero.

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

import structlog

from src.core.context import current_tracker
from src.infrastructure.observability.metrics_usage_limits import (
    google_api_calls_unaccounted_total,
)

logger = structlog.get_logger(__name__)


def track_google_api_call(
    api_name: str, endpoint: str, cached: bool = False, units: int = 1
) -> None:
    """
    Track a Google API call in the ambient TrackingContext.

    Uses ContextVar to find tracker - no need to pass explicitly. Safe to call
    from anywhere; a billed call made with no tracker is counted as
    unaccounted rather than dropped.

    Note: Synchronous because it uses pre-loaded pricing cache (no DB/API calls needed).

    Args:
        api_name: API name (e.g., "places", "routes", "geocoding")
        endpoint: Endpoint path (e.g., "/places:searchText", "/directions/v2:computeRoutes")
        cached: True if result was served from cache (zero cost)
        units: Billable events this call is -- 1 for a request, the element
            count for a Route Matrix, which Google bills per element returned.

    Example:
        >>> # In a Google client method after making an API call:
        >>> track_google_api_call("places", "/places:searchText", cached=False)
        >>>
        >>> # For cached results:
        >>> track_google_api_call("places", "/places:searchText", cached=True)
    """
    tracker = current_tracker.get()
    if tracker is not None:
        tracker.record_google_api_call(
            api_name=api_name,
            endpoint=endpoint,
            cached=cached,
            units=units,
        )
        return
    if cached:
        # Redis answered; Google billed nothing. Nothing to file, nothing lost.
        return
    google_api_calls_unaccounted_total.labels(api_name=api_name).inc(units)
    logger.warning("google_api_call_unaccounted", api_name=api_name, endpoint=endpoint, units=units)
