"""
Prometheus metrics for browser automation.

Tracks active sessions, actions, navigation latency, accessibility tree size,
errors, and memory usage for the browser control feature.

Phase: evolution F7 — Browser Control (Playwright)
"""

from prometheus_client import Counter, Gauge, Histogram

# Active browser sessions across all workers (set by pool)
browser_sessions_active = Gauge(
    "browser_sessions_active",
    "Number of currently active browser sessions",
)

# Browser actions counter (by type and outcome)
browser_actions_total = Counter(
    "browser_actions_total",
    "Total browser actions executed",
    ["action_type", "status"],
)

# Navigation latency (page load time)
browser_navigation_duration_seconds = Histogram(
    "browser_navigation_duration_seconds",
    "Time to load a page in the browser",
    buckets=[0.5, 1, 2, 3, 5, 10, 15, 30],
)

# Accessibility tree size (estimated tokens)
browser_snapshot_tokens = Histogram(
    "browser_snapshot_tokens",
    "Estimated token count of accessibility tree snapshots",
    buckets=[100, 500, 1000, 2000, 3000, 5000, 10000],
)

# Browser errors by type
browser_errors_total = Counter(
    "browser_errors_total",
    "Total browser errors",
    ["error_type"],
)

# Browser process memory usage (bytes)
browser_memory_bytes = Gauge(
    "browser_memory_bytes",
    "Browser process memory usage in bytes",
)
