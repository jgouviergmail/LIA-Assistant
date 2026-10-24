"""
Prometheus metrics for Redis rate limiting.

Implements comprehensive observability for Redis-based distributed rate limiter:
- Rate limit decisions (allows vs denials)
- Rate limit check latency
- Sliding window sizes
- Connection pool health
- Lua script execution
- Error tracking

Phase: PHASE 2.4 - Redis Rate Limiter Observability
Created: 2025-11-22
"""

import ipaddress
import re

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# REDIS RATE LIMITING METRICS
# ============================================================================

redis_rate_limit_allows_total = Counter(
    "redis_rate_limit_allows_total",
    "Total rate limit allows (accepted requests)",
    ["key_prefix"],  # e.g., "user", "api", "endpoint"
    # Use key_prefix instead of full key to avoid high cardinality
    # Extract prefix like "user:*:contacts_search" → "user_contacts_search"
)

redis_rate_limit_hits_total = Counter(
    "redis_rate_limit_hits_total",
    "Total rate limit hits (rejected requests)",
    ["key_prefix"],  # e.g., "user", "api", "endpoint"
)

redis_rate_limit_check_duration_seconds = Histogram(
    "redis_rate_limit_check_duration_seconds",
    "Duration of rate limit check in Redis (including Lua script execution)",
    ["key_prefix"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    # Most checks should be <10ms; anything >100ms indicates Redis performance issue
)

redis_sliding_window_requests_current = Gauge(
    "redis_sliding_window_requests_current",
    "Current number of requests in sliding window",
    ["key_prefix"],
    # Sampled during rate limit checks
    # Useful for understanding current usage vs limits
    multiprocess_mode="mostrecent",
)

redis_connection_pool_size_current = Gauge(
    "redis_connection_pool_size_current",
    "Current Redis connection pool size",
    # No labels - single global pool
    multiprocess_mode="mostrecent",
)

redis_connection_pool_available_current = Gauge(
    "redis_connection_pool_available_current",
    "Available connections in Redis pool",
    # No labels - single global pool
    multiprocess_mode="livesum",
)

redis_rate_limit_errors_total = Counter(
    "redis_rate_limit_errors_total",
    "Errors during rate limit checks",
    ["error_type"],  # e.g., "ConnectionError", "TimeoutError", "ScriptError"
)

redis_lua_script_executions_total = Counter(
    "redis_lua_script_executions_total",
    "Lua script executions for atomic rate limiting",
    ["script_name", "status"],  # script_name="sliding_window", status="success"|"error"
)


#: An account id as the limiters write it (``str(uuid)``), any case.
_UUID_SEGMENT = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def _is_address(text: str) -> bool:
    """Whether ``text`` is an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _without_address_tail(parts: list[str]) -> list[str]:
    """Drop the client address a per-client key ends with.

    An IPv6 address contains the ``:`` the key is split on, so it is found as
    the longest tail of segments that parses as one address.
    """
    for start in range(len(parts)):
        if _is_address(":".join(parts[start:])):
            return parts[:start]
    return parts


def extract_key_prefix(key: str) -> str:
    """
    Extract rate limit key prefix to avoid high cardinality.

    A rate-limit key names who it throttles — a client IP, an account id — and
    a metric label must never do so: it would grow with every visitor and put
    an identifier in Prometheus (measured on production 2026-10-23: 27 of 56
    series carried an IP, 25 an account id). Numeric segments, account ids and
    the trailing client address are dropped; the bounded words are kept:

    - "user:123:contacts_search" → "user_contacts_search"
    - "auth:login:203.0.113.7" → "auth_login"
    - "user:<uuid>:google_calendar" → "user_google_calendar"
    - "endpoint:/api/v1/contacts" → "endpoint__api_v1_contacts"

    Args:
        key: Full rate limit key

    Returns:
        Sanitized key prefix for metrics labels

    Examples:
        >>> extract_key_prefix("user:123:contacts_search")
        'user_contacts_search'
        >>> extract_key_prefix("http:global:2001:db8:85a3::8a2e:370:7334")
        'http_global'
        >>> extract_key_prefix("api:gmail:send")
        'api_gmail_send'
    """
    parts = key.split(":")
    if len(parts) >= 2:
        prefix_parts = [
            p
            for p in _without_address_tail(parts)
            if not p.isdigit() and not _is_address(p) and not _UUID_SEGMENT.fullmatch(p)
        ]
        # Join with underscore for Prometheus label compatibility
        return "_".join(prefix_parts).replace("/", "_").replace("-", "_")
    return "unknown"
