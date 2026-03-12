"""
Prometheus metrics for database performance and reliability.

Tracks database query performance, errors, and connection pool health for:
- Per-repository query latency (identify slow queries, N+1 patterns)
- Database error taxonomy (deadlocks, timeouts, constraint violations)
- Connection pool saturation (prevent 503 errors)
- Transaction duration (detect long-running transactions)

Critical for incident response and performance optimization.

Reference:
- PostgreSQL monitoring best practices
- SQLAlchemy performance patterns
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# QUERY PERFORMANCE METRICS
# ============================================================================

repository_query_duration_seconds = Histogram(
    "repository_query_duration_seconds",
    "Database query latency per repository method",
    ["repository", "method", "query_type"],
    # Buckets optimized for typical database query patterns
    # Most queries should be < 100ms, slow queries > 500ms need investigation
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

db_query_errors_total = Counter(
    "db_query_errors_total",
    "Database query errors by type",
    ["repository", "error_type"],
    # error_type: deadlock, timeout, constraint_violation, serialization_failure, unknown
)

# ============================================================================
# CONNECTION POOL METRICS
# ============================================================================

db_connection_pool_size = Gauge(
    "db_connection_pool_size",
    "Total size of database connection pool",
)

db_connection_pool_checkedout = Gauge(
    "db_connection_pool_checkedout",
    "Number of connections currently checked out from pool",
)

db_connection_pool_overflow = Gauge(
    "db_connection_pool_overflow",
    "Number of overflow connections beyond pool size",
)

db_connection_pool_waiting_total = Gauge(
    "db_connection_pool_waiting_total",
    "Number of requests waiting for a connection (saturation indicator)",
)

db_connection_pool_exhausted_total = Counter(
    "db_connection_pool_exhausted_total",
    "Total times connection pool was exhausted (all connections in use)",
)

# ============================================================================
# TRANSACTION METRICS
# ============================================================================

db_transaction_duration_seconds = Histogram(
    "db_transaction_duration_seconds",
    "Database transaction duration (session start to commit)",
    ["endpoint", "transaction_type"],
    # transaction_type: read, write
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

db_transaction_rollback_total = Counter(
    "db_transaction_rollback_total",
    "Total database transaction rollbacks",
    ["endpoint", "reason"],
    # reason: application_error, integrity_error, deadlock, timeout
)
