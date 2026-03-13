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
)

redis_connection_pool_size_current = Gauge(
    "redis_connection_pool_size_current",
    "Current Redis connection pool size",
    # No labels - single global pool
)

redis_connection_pool_available_current = Gauge(
    "redis_connection_pool_available_current",
    "Available connections in Redis pool",
    # No labels - single global pool
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


def extract_key_prefix(key: str) -> str:
    """
    Extract rate limit key prefix to avoid high cardinality.

    Transforms full keys into prefixes for metrics labeling:
    - "user:123:contacts_search" → "user_contacts_search"
    - "api:gmail:send" → "api_gmail_send"
    - "endpoint:/api/v1/contacts" → "endpoint_contacts"

    This prevents cardinality explosion (thousands of user IDs)
    while maintaining useful grouping for monitoring.

    Args:
        key: Full rate limit key

    Returns:
        Sanitized key prefix for metrics labels

    Examples:
        >>> extract_key_prefix("user:123:contacts_search")
        'user_contacts_search'
        >>> extract_key_prefix("api:gmail:send")
        'api_gmail_send'
        >>> extract_key_prefix("endpoint:/api/v1/contacts")
        'endpoint_contacts'
    """
    parts = key.split(":")
    if len(parts) >= 2:
        # Remove numeric IDs (user:123 → user, api:gmail → api_gmail)
        prefix_parts = [p for p in parts if not p.isdigit()]
        # Join with underscore for Prometheus label compatibility
        return "_".join(prefix_parts).replace("/", "_").replace("-", "_")
    return "unknown"
