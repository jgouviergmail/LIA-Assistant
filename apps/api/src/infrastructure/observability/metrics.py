"""
Prometheus metrics configuration for FastAPI.
"""

import re
import time
from collections.abc import Awaitable, Callable

import structlog
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.field_names import FIELD_NODE_NAME

logger = structlog.get_logger(__name__)

# HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"],
    multiprocess_mode="livesum",
)

# Authentication metrics
auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total authentication attempts",
    ["method", "status"],
)

# NOTE: Database metrics moved to metrics_database.py
# db_connections_active renamed to db_connection_pool_checkedout (more accurate naming)
# See metrics_database.py for comprehensive database performance metrics

# LangGraph/Agents metrics
# NOTE: graph_executions_total and graph_execution_duration_seconds removed
# These legacy metrics were replaced by comprehensive SSE streaming metrics in metrics_agents.py:
# - sse_streaming_duration_seconds (replaces graph_execution_duration_seconds)
# - agent_node_executions_total (tracks per-node execution)
# - sse_tokens_generated_total (tracks streaming progress)

router_confidence_score = Histogram(
    "router_confidence_score",
    "Router confidence score distribution",
    ["intention"],
    buckets=[0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# NOTE: llm_tokens_used_total was replaced by llm_tokens_consumed_total
# in metrics_agents.py (modern token tracking implementation)

# NOTE: sse_connections_active and sse_heartbeats_sent_total removed (never instrumented)
# SSE connection monitoring done via http_requests_in_progress gauge
# Heartbeat feature not implemented (SSE streams are short-lived, complete responses)

graph_exceptions_total = Counter(
    "graph_exceptions_total",
    "Total exceptions in graph execution",
    [FIELD_NODE_NAME, "exception_type"],
)

# ============================================================================
# CACHE METRICS
# ============================================================================

cache_hit_total = Counter(
    "cache_hit_total",
    "Total cache hits",
    ["cache_type"],  # contacts_list, contacts_search, contacts_details, pricing, etc.
)

cache_miss_total = Counter(
    "cache_miss_total",
    "Total cache misses",
    ["cache_type"],
)


# NOTE: cache_size_bytes and cache_evictions_total removed (never instrumented)
# Redis cache size monitoring should be done via Redis INFO command externally
# TTL-based evictions are automatic in Redis and don't need app-level tracking

# ============================================================================
# OAUTH LOCK METRICS
# ============================================================================

oauth_lock_wait_duration_seconds = Histogram(
    "oauth_lock_wait_duration_seconds",
    "Time spent waiting to acquire OAuth lock",
    ["connector_type"],  # gmail, google_contacts, etc.
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

oauth_lock_timeout_total = Counter(
    "oauth_lock_timeout_total",
    "Total OAuth lock acquisition timeouts",
    ["connector_type"],
)

oauth_lock_acquired_total = Counter(
    "oauth_lock_acquired_total",
    "Total successful OAuth lock acquisitions",
    ["connector_type"],
)

oauth_lock_released_total = Counter(
    "oauth_lock_released_total",
    "Total OAuth lock releases",
    ["connector_type"],
)

oauth_lock_contention_total = Counter(
    "oauth_lock_contention_total",
    "Total lock contention events (multiple waiters)",
    ["connector_type"],
)

# Note: All legacy button-based tool approval metrics removed - replaced by conversational HITL in metrics_agents.py
# - tool_approval_pending_total (removed)
# - tool_approval_response_time_seconds (removed)
# - tool_approval_timeout_total (removed)
# - tool_approval_decision_total (removed)
# - tool_execution_duration_seconds (removed - redundant with agent_tool_duration_seconds in metrics_agents.py)

# ============================================================================
# CONNECTOR HEALTH METRICS
# ============================================================================

connector_api_requests_total = Counter(
    "connector_api_requests_total",
    "Total external API requests to connector services",
    ["connector_type", "operation", "status"],  # status: success, error, timeout
)

connector_api_duration_seconds = Histogram(
    "connector_api_duration_seconds",
    "External connector API request duration",
    ["connector_type", "operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

connector_api_errors_total = Counter(
    "connector_api_errors_total",
    "Total connector API errors",
    ["connector_type", "error_type"],  # error_type: rate_limit, auth_error, network_error, etc.
)

connector_token_refresh_total = Counter(
    "connector_token_refresh_total",
    "Total OAuth token refresh operations",
    ["connector_type", "status"],  # status: success, failure
)

connector_api_key_verification_total = Counter(
    "connector_api_key_verification_total",
    "API-key connector functional verifications before activation (audit F034)",
    # result: verified | rejected | timeout | format_only (no functional verifier)
    ["connector_type", "result"],
)

connector_error_notices_total = Counter(
    "connector_error_notices_total",
    "Actionable connector error notices emitted to the chat stream (Lot 3 P3)",
    ["connector_type", "action"],  # action: reconnect | rate_limit
)

# NOTE: Generic repository metrics removed (never instrumented, too high cardinality risk)
# Use domain-specific metrics instead (e.g., conversation_repository_queries_total in conversations)
# Database-level monitoring should use external tools (pg_stat_statements, pganalyze)
#
# Removed metrics:
# - repository_operation_duration_seconds (never instrumented)
# - repository_bulk_operation_total (never instrumented)
# - repository_soft_delete_total (never instrumented)

# ============================================================================
# HTTP RATE LIMITING METRICS
# ============================================================================

http_rate_limit_hits_total = Counter(
    "http_rate_limit_hits_total",
    "Total HTTP requests blocked by rate limiting (429 responses)",
    ["endpoint", "endpoint_type"],  # endpoint_type: auth_login, auth_register, sse, default
)

# SEC-031. `reason` distinguishes a request refused on its declared
# Content-Length (cheap, nothing buffered) from one cut mid-stream because the
# real byte count crossed the ceiling — the latter meaning a client understated
# its length or used chunked encoding. The label is the ROUTE TEMPLATE, never
# the raw path: a per-URL label on an attacker-chosen path is unbounded
# cardinality, which is how a metric takes down the very Prometheus meant to
# watch it.
# SEC-016. The global limiter fails OPEN when Redis is unavailable — on a
# single-instance deployment, failing closed turns a cache outage into a total
# outage. This counter is what keeps that trade-off honest: it measures how long
# the API ran unprotected, so the degraded window is visible instead of silent.
http_rate_limit_degraded_total = Counter(
    "http_rate_limit_degraded_total",
    "Requests admitted without a rate-limit check because the limiter was unavailable",
)

http_request_body_rejected_total = Counter(
    "http_request_body_rejected_total",
    "Total HTTP requests rejected for exceeding the global body size limit",
    ["reason"],  # reason: declared_length, streamed_bytes
)

# ============================================================================
# BUSINESS METRICS (User Activity & Engagement)
# ============================================================================

user_registrations_total = Counter(
    "user_registrations_total",
    "Total user registrations (new account creations)",
    ["provider", "status"],  # provider: password, google | status: success, error
)

user_logins_total = Counter(
    "user_logins_total",
    "Total user login attempts and successes",
    ["provider", "status"],  # provider: password, google | status: success, error
)

user_active_daily_gauge = Gauge(
    "user_active_daily_gauge",
    "Number of daily active users (DAU) - users with activity in last 24h",
    multiprocess_mode="mostrecent",
)

user_active_weekly_gauge = Gauge(
    "user_active_weekly_gauge",
    "Number of weekly active users (WAU) - users with activity in last 7 days",
    multiprocess_mode="mostrecent",
)

# GeoIP metrics (low cardinality — country only, ~200 unique values max)
http_requests_by_country_total = Counter(
    "http_requests_by_country_total",
    "Total HTTP requests by country (ISO 3166-1 alpha-2)",
    ["country"],
)

conversation_length_messages = Histogram(
    "conversation_length_messages",
    "Number of messages in completed conversations (distribution)",
    buckets=[1, 2, 3, 5, 10, 15, 20, 30, 50, 100],
)

# ============================================================================
# EXPLOITATION METRICS (Infrastructure Health)
# ============================================================================

# NOTE: Database connection pool metrics moved to metrics_database.py
# All db_connection_pool_* metrics are now in metrics_database.py for better organization:
# - db_connection_pool_size (Gauge)
# - db_connection_pool_checkedout (Gauge) - renamed from db_connections_active
# - db_connection_pool_overflow (Gauge)
# - db_connection_pool_waiting_total (Gauge)
# - db_connection_pool_exhausted_total (Counter)


background_job_duration_seconds = Histogram(
    "background_job_duration_seconds",
    "Background job execution duration (scheduled tasks, workers)",
    ["job_name"],  # job_name: currency_sync, cleanup_sessions, etc.
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
)

background_job_errors_total = Counter(
    "background_job_errors_total",
    "Total background job errors",
    ["job_name"],
)

# ============================================================================
# HYBRID MEMORY SEARCH METRICS
# ============================================================================

hybrid_search_total = Counter(
    "memory_hybrid_search_total",
    "Total hybrid search operations",
    ["status"],  # success, error, fallback
)

hybrid_search_duration_seconds = Histogram(
    "memory_hybrid_search_duration_seconds",
    "Hybrid search latency",
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0],
)

bm25_cache_hits_total = Counter(
    "memory_bm25_cache_hits_total",
    "BM25 index cache hits",
)

bm25_cache_misses_total = Counter(
    "memory_bm25_cache_misses_total",
    "BM25 index cache misses",
)

bm25_cache_size = Gauge(
    "memory_bm25_cache_size",
    "Current BM25 cache size (users)",
    multiprocess_mode="livesum",
)


# Cardinality guard (F27, 2026-07): path params (UUIDs, ids) and bot scans
# used to flow RAW into the endpoint label of 3 metric families (one series
# per UUID, never freed from the registry — amplified by the ADR-089
# multiprocess mmap files). Segments that look like identifiers collapse to
# "{id}"; the exact route template (available only AFTER routing) is
# preferred for the counter/histogram, with "unmatched" for 404s/scans.
_ID_SEGMENT_RE = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{24,}"
    r"|\d+)$"
)


def _normalize_path_fallback(path: str) -> str:
    """Collapse identifier-looking path segments to bound label cardinality.

    Used where the route template is not yet known (in-progress gauge is
    incremented BEFORE routing). E.g. /api/v1/journals/9b2e…f1 → /api/v1/journals/{id}.
    """
    return "/".join("{id}" if _ID_SEGMENT_RE.match(seg) else seg for seg in path.split("/"))


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        # Route template unknown before routing: normalized-path fallback.
        # inc/dec MUST use the same label value (hence one variable).
        in_progress_endpoint = _normalize_path_fallback(request.url.path)

        # Track request in progress
        http_requests_in_progress.labels(method=method, endpoint=in_progress_endpoint).inc()

        start_time = time.perf_counter()
        try:
            response = await call_next(request)

            # AFTER routing the matched route template is available — the
            # exact, cardinality-bounded label. Unmatched paths (404s, bot
            # scans) collapse into a single series.
            endpoint = getattr(request.scope.get("route"), "path", None) or "unmatched"

            # Record request
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()

            # NOTE: update_db_pool_metrics() used to run here on EVERY request
            # (despite its "periodically" comment) — it now runs in the
            # lifetime-metrics background updater (30s interval).

            return response

        finally:
            # Duration observed on success AND exception paths (parity with
            # the historical `with histogram.time():` context manager). The
            # route is read here: it is set once routing happened, even when
            # the endpoint later raised.
            duration = time.perf_counter() - start_time
            final_endpoint = getattr(request.scope.get("route"), "path", None) or "unmatched"
            http_request_duration_seconds.labels(
                method=method,
                endpoint=final_endpoint,
            ).observe(duration)

            # Decrement in-progress counter
            http_requests_in_progress.labels(method=method, endpoint=in_progress_endpoint).dec()


def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint.

    Returns:
        Response with metrics in Prometheus format
    """
    metrics_data = generate_latest()
    return Response(
        content=metrics_data,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
