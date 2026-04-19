"""Prometheus metrics for heartbeat proactive notifications.

Covers the Phase 3 last-known location cascade:
- Counter: which location source (home vs last-known) served a given
  heartbeat weather notification.
- Counter: PUT /me/last-location outcomes (accepted / throttled / forbidden).
- Counter: reverse-geocoding cache/API outcomes.
"""

from __future__ import annotations

from prometheus_client import Counter

heartbeat_weather_location_source_total = Counter(
    "heartbeat_weather_location_source_total",
    "Which location source was used for a proactive weather notification.",
    ["source"],
    # source: home | last_known
)

user_location_put_total = Counter(
    "user_location_put_total",
    "Outcomes of the PUT /auth/me/last-location endpoint.",
    ["result"],
    # result: accepted | throttled | forbidden
)

user_location_geocode_total = Counter(
    "user_location_geocode_total",
    "Reverse-geocoding outcomes for heartbeat notifications.",
    ["result"],
    # result: cache_hit | api_hit | api_error | redis_down
)
