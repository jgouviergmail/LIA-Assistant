"""Helper for tracking Google API calls from clients.

This module provides a simple function to track Google API calls using
the ContextVar pattern. It's designed to be called from anywhere in the
async call stack without explicit tracker parameter passing.

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from src.core.context import current_tracker


def track_google_api_call(api_name: str, endpoint: str, cached: bool = False) -> None:
    """
    Track a Google API call if within a TrackingContext.

    Uses ContextVar to find tracker - no need to pass explicitly.
    Safe to call from anywhere - does nothing if no tracker active.

    Note: Synchronous because it uses pre-loaded pricing cache (no DB/API calls needed).

    Args:
        api_name: API name (e.g., "places", "routes", "geocoding")
        endpoint: Endpoint path (e.g., "/places:searchText", "/directions/v2:computeRoutes")
        cached: True if result was served from cache (zero cost)

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
        )
