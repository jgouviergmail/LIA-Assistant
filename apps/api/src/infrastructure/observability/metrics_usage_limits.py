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
