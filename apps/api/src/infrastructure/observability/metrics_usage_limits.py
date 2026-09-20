"""
Prometheus metrics for usage limits enforcement.

Tracks usage limit checks and enforcement actions across all layers.

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from prometheus_client import Counter

# Total usage limit checks performed (by result: ok, warning, critical, blocked_limit, blocked_manual)
usage_limit_check_total = Counter(
    "usage_limit_check_total",
    "Total usage limit checks performed",
    ["result"],
)

# Total enforcement actions (user blocked from performing an action)
usage_limit_enforcement_total = Counter(
    "usage_limit_enforcement_total",
    "Total enforcement actions (user blocked from action)",
    ["layer", "limit_type"],
)

# A Google Maps Platform call (Places, Routes, Geocoding, Weather, Air
# quality, Static Maps, Street View) made where NO tracker was accounting for
# it. The deployment paid it and nobody filed it: the counter in
# ``google_api_tracker`` used to « do nothing » without an ambient
# ``TrackingContext``, so every paid call outside a chat turn left no ledger
# row (measured 2026-09-19: 3 020 usage rows, none outside a turn). Every
# out-of-turn surface now opens its own accounting; this series is the proof,
# and its expected value is zero.
google_api_calls_unaccounted_total = Counter(
    "google_api_calls_unaccounted_total",
    "Paid Google Maps Platform calls made with no accounting context — a euro "
    "the deployment paid that reached no ledger. Expected 0; any rise names a "
    "surface that reaches a paid client outside a TrackingContext.",
    ["api_name"],
)
