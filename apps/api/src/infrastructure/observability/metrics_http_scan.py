"""Bounded-cardinality signals for HTTP scan protection; never label by IP/path."""

from prometheus_client import Counter

http_scan_bans_total = Counter("http_scan_bans_total", "New temporary HTTP scan bans", ["reason"])
http_scan_blocked_total = Counter("http_scan_blocked_total", "Requests refused by an HTTP scan ban")
http_scan_degraded_total = Counter(
    "http_scan_degraded_total", "Fail-open HTTP scan checks", ["operation"]
)
