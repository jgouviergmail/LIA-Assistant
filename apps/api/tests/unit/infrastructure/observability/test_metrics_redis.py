"""
Unit tests for Redis rate limiting Prometheus metrics module.

Phase: PHASE 2.4 - Redis Rate Limiter Observabilité Complète
Session: 4
Created: 2025-11-22
Target: Test 8 Redis rate limiting metrics
"""

from src.infrastructure.observability.metrics_redis import (
    extract_key_prefix,
    redis_connection_pool_available_current,
    redis_connection_pool_size_current,
    redis_lua_script_executions_total,
    redis_rate_limit_allows_total,
    redis_rate_limit_check_duration_seconds,
    redis_rate_limit_errors_total,
    redis_rate_limit_hits_total,
    redis_sliding_window_requests_current,
)


class TestExtractKeyPrefix:
    """Tests for extract_key_prefix function (cardinality reduction)."""

    def test_extract_prefix_from_user_key(self):
        """Test extracting prefix from user key (user:123:contacts_search → user_contacts_search)."""
        # Standard user key pattern
        key = "user:123:contacts_search"

        # Extract prefix (remove numeric ID)
        prefix = extract_key_prefix(key)

        # Should remove numeric ID, keep semantic parts
        assert prefix == "user_contacts_search"

    def test_extract_prefix_from_api_key(self):
        """Test extracting prefix from API endpoint key (api:gmail:send → api_gmail_send)."""
        key = "api:gmail:send"

        prefix = extract_key_prefix(key)

        # Should replace colons with underscores
        assert prefix == "api_gmail_send"

    def test_extract_prefix_with_multiple_segments(self):
        """Test extracting prefix with multiple segments (user:456:domain:contacts:list)."""
        key = "user:456:domain:contacts:list"

        prefix = extract_key_prefix(key)

        # Should remove numeric ID, keep all semantic segments
        assert prefix == "user_domain_contacts_list"

    def test_extract_prefix_handles_slashes(self):
        """Test that slashes are replaced with underscores (endpoint:/api/v1/contacts)."""
        key = "endpoint:/api/v1/contacts"

        prefix = extract_key_prefix(key)

        # Slashes replaced with underscores
        assert prefix == "endpoint__api_v1_contacts"

    def test_extract_prefix_handles_hyphens(self):
        """Test that hyphens are replaced with underscores (api:rate-limit:key)."""
        key = "api:rate-limit:key"

        prefix = extract_key_prefix(key)

        # Hyphens replaced with underscores
        assert prefix == "api_rate_limit_key"

    def test_extract_prefix_single_segment(self):
        """Test single segment key (test → unknown)."""
        key = "test"

        prefix = extract_key_prefix(key)

        # Single segment returns "unknown" (no semantic structure)
        assert prefix == "unknown"

    def test_extract_prefix_mixed_numeric_alphabetic(self):
        """Test mixed numeric/alphabetic segments (user:abc123:action)."""
        key = "user:abc123:action"

        prefix = extract_key_prefix(key)

        # abc123 is not pure numeric, so kept
        assert prefix == "user_abc123_action"

    def test_extract_prefix_preserves_non_numeric_segments(self):
        """Test that non-numeric segments are preserved (tenant:prod:user:789:search)."""
        key = "tenant:prod:user:789:search"

        prefix = extract_key_prefix(key)

        # Numeric "789" removed, others kept
        assert prefix == "tenant_prod_user_search"


class TestRedisRateLimitMetrics:
    """Tests for Redis rate limiting Prometheus metrics."""

    def test_redis_rate_limit_allows_total_metric_exists(self):
        """Test that redis_rate_limit_allows_total counter is registered."""
        # Metric should be registered in Prometheus registry
        assert redis_rate_limit_allows_total is not None

        # Verify metric can be used
        metric = redis_rate_limit_allows_total.labels(key_prefix="test")
        assert metric is not None

    def test_redis_rate_limit_allows_total_has_key_prefix_label(self):
        """Test that redis_rate_limit_allows_total has key_prefix label."""
        # Label names should include 'key_prefix'
        assert "key_prefix" in redis_rate_limit_allows_total._labelnames

    def test_redis_rate_limit_allows_total_increment(self):
        """Test incrementing redis_rate_limit_allows_total counter."""
        # Get initial value
        metric = redis_rate_limit_allows_total.labels(key_prefix="user_contacts_search")
        initial_value = metric._value.get()

        # Increment counter
        metric.inc()

        # Value should increase by 1
        assert metric._value.get() == initial_value + 1

    def test_redis_rate_limit_hits_total_metric_exists(self):
        """Test that redis_rate_limit_hits_total counter is registered."""
        assert redis_rate_limit_hits_total is not None
        metric = redis_rate_limit_hits_total.labels(key_prefix="test")
        assert metric is not None

    def test_redis_rate_limit_hits_total_has_key_prefix_label(self):
        """Test that redis_rate_limit_hits_total has key_prefix label."""
        assert "key_prefix" in redis_rate_limit_hits_total._labelnames

    def test_redis_rate_limit_hits_total_increment(self):
        """Test incrementing redis_rate_limit_hits_total counter."""
        metric = redis_rate_limit_hits_total.labels(key_prefix="api_gmail_send")
        initial_value = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial_value + 1

    def test_redis_rate_limit_check_duration_seconds_metric_exists(self):
        """Test that redis_rate_limit_check_duration_seconds histogram is registered."""
        assert redis_rate_limit_check_duration_seconds is not None
        assert (
            redis_rate_limit_check_duration_seconds._name
            == "redis_rate_limit_check_duration_seconds"
        )
        assert redis_rate_limit_check_duration_seconds._type == "histogram"

    def test_redis_rate_limit_check_duration_seconds_has_key_prefix_label(self):
        """Test that duration histogram has key_prefix label."""
        assert "key_prefix" in redis_rate_limit_check_duration_seconds._labelnames

    def test_redis_rate_limit_check_duration_seconds_observe(self):
        """Test observing latency in redis_rate_limit_check_duration_seconds histogram."""
        metric = redis_rate_limit_check_duration_seconds.labels(key_prefix="user_contacts_search")

        # Observe sample latency (5ms = 0.005s)
        metric.observe(0.005)

        # Histogram should have recorded the observation
        # Check _sum increased
        assert metric._sum.get() >= 0.005

    def test_redis_rate_limit_check_duration_seconds_has_correct_buckets(self):
        """Test that duration histogram has appropriate buckets for sub-10ms latencies."""
        # Expected buckets for Redis latency: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        # Get buckets from histogram (access via _upper_bounds on child metric)
        metric = redis_rate_limit_check_duration_seconds.labels(key_prefix="test")
        buckets = metric._upper_bounds

        # Should have granular buckets for sub-10ms measurement
        assert 0.001 in buckets  # 1ms
        assert 0.005 in buckets  # 5ms
        assert 0.01 in buckets  # 10ms

    def test_redis_sliding_window_requests_current_metric_exists(self):
        """Test that redis_sliding_window_requests_current gauge is registered."""
        assert redis_sliding_window_requests_current is not None
        assert (
            redis_sliding_window_requests_current._name == "redis_sliding_window_requests_current"
        )
        assert redis_sliding_window_requests_current._type == "gauge"

    def test_redis_sliding_window_requests_current_has_key_prefix_label(self):
        """Test that sliding window gauge has key_prefix label."""
        assert "key_prefix" in redis_sliding_window_requests_current._labelnames

    def test_redis_sliding_window_requests_current_set(self):
        """Test setting redis_sliding_window_requests_current gauge value."""
        metric = redis_sliding_window_requests_current.labels(key_prefix="user_emails_send")

        # Set current window size
        metric.set(42)

        # Value should be 42
        assert metric._value.get() == 42

    def test_redis_connection_pool_size_current_metric_exists(self):
        """Test that redis_connection_pool_size_current gauge is registered."""
        assert redis_connection_pool_size_current is not None
        assert redis_connection_pool_size_current._name == "redis_connection_pool_size_current"
        assert redis_connection_pool_size_current._type == "gauge"

    def test_redis_connection_pool_size_current_no_labels(self):
        """Test that pool size gauge has no labels (global metric)."""
        # Should have empty labelnames (no key_prefix, global metric)
        assert redis_connection_pool_size_current._labelnames == ()

    def test_redis_connection_pool_size_current_set(self):
        """Test setting redis_connection_pool_size_current gauge value."""
        # Set pool size
        redis_connection_pool_size_current.set(100)

        # Value should be 100
        assert redis_connection_pool_size_current._value.get() == 100

    def test_redis_connection_pool_available_current_metric_exists(self):
        """Test that redis_connection_pool_available_current gauge is registered."""
        assert redis_connection_pool_available_current is not None
        assert (
            redis_connection_pool_available_current._name
            == "redis_connection_pool_available_current"
        )
        assert redis_connection_pool_available_current._type == "gauge"

    def test_redis_connection_pool_available_current_no_labels(self):
        """Test that available connections gauge has no labels (global metric)."""
        assert redis_connection_pool_available_current._labelnames == ()

    def test_redis_connection_pool_available_current_set(self):
        """Test setting redis_connection_pool_available_current gauge value."""
        redis_connection_pool_available_current.set(75)

        assert redis_connection_pool_available_current._value.get() == 75

    def test_redis_rate_limit_errors_total_metric_exists(self):
        """Test that redis_rate_limit_errors_total counter is registered."""
        assert redis_rate_limit_errors_total is not None
        metric = redis_rate_limit_errors_total.labels(error_type="TestError")
        assert metric is not None

    def test_redis_rate_limit_errors_total_has_error_type_label(self):
        """Test that errors counter has error_type label."""
        assert "error_type" in redis_rate_limit_errors_total._labelnames

    def test_redis_rate_limit_errors_total_increment(self):
        """Test incrementing redis_rate_limit_errors_total counter."""
        metric = redis_rate_limit_errors_total.labels(error_type="TimeoutError")
        initial_value = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial_value + 1

    def test_redis_rate_limit_errors_total_multiple_error_types(self):
        """Test tracking different error types separately."""
        # Increment ConnectionError
        redis_rate_limit_errors_total.labels(error_type="ConnectionError").inc()
        conn_error_value = redis_rate_limit_errors_total.labels(
            error_type="ConnectionError"
        )._value.get()

        # Increment TimeoutError
        redis_rate_limit_errors_total.labels(error_type="TimeoutError").inc()
        timeout_error_value = redis_rate_limit_errors_total.labels(
            error_type="TimeoutError"
        )._value.get()

        # Each error type should be tracked independently
        assert conn_error_value >= 1
        assert timeout_error_value >= 1

    def test_redis_lua_script_executions_total_metric_exists(self):
        """Test that redis_lua_script_executions_total counter is registered."""
        assert redis_lua_script_executions_total is not None
        metric = redis_lua_script_executions_total.labels(script_name="test", status="success")
        assert metric is not None

    def test_redis_lua_script_executions_total_has_labels(self):
        """Test that Lua script counter has script_name and status labels."""
        assert "script_name" in redis_lua_script_executions_total._labelnames
        assert "status" in redis_lua_script_executions_total._labelnames

    def test_redis_lua_script_executions_total_success_increment(self):
        """Test incrementing Lua script executions for success status."""
        metric = redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="success"
        )
        initial_value = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial_value + 1

    def test_redis_lua_script_executions_total_error_increment(self):
        """Test incrementing Lua script executions for error status."""
        metric = redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="error"
        )
        initial_value = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial_value + 1

    def test_redis_lua_script_executions_total_tracks_status_separately(self):
        """Test that success and error statuses are tracked independently."""
        # Increment success
        redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="success"
        ).inc()
        success_value = redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="success"
        )._value.get()

        # Increment error
        redis_lua_script_executions_total.labels(script_name="sliding_window", status="error").inc()
        error_value = redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="error"
        )._value.get()

        # Each status should be independent
        assert success_value >= 1
        assert error_value >= 1


class TestMetricsIntegration:
    """Integration tests for Redis metrics (simulate real usage patterns)."""

    def test_rate_limit_allow_scenario(self):
        """Test metrics updates for a rate limit allow scenario."""
        key_prefix = "test_user_search"

        # Simulate rate limit allow
        redis_rate_limit_allows_total.labels(key_prefix=key_prefix).inc()
        redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).observe(0.003)
        redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="success"
        ).inc()

        # Verify metrics recorded
        assert redis_rate_limit_allows_total.labels(key_prefix=key_prefix)._value.get() >= 1
        assert (
            redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix)._sum.get()
            >= 0.003
        )
        assert (
            redis_lua_script_executions_total.labels(
                script_name="sliding_window", status="success"
            )._value.get()
            >= 1
        )

    def test_rate_limit_hit_scenario(self):
        """Test metrics updates for a rate limit hit (rejection) scenario."""
        key_prefix = "test_api_endpoint"

        # Simulate rate limit hit (rejected)
        redis_rate_limit_hits_total.labels(key_prefix=key_prefix).inc()
        redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).observe(0.002)
        redis_lua_script_executions_total.labels(
            script_name="sliding_window", status="success"
        ).inc()

        # Verify metrics recorded
        assert redis_rate_limit_hits_total.labels(key_prefix=key_prefix)._value.get() >= 1

    def test_rate_limit_error_scenario(self):
        """Test metrics updates for a rate limit error scenario."""
        key_prefix = "test_error_endpoint"

        # Simulate Redis error
        redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).observe(0.050)
        redis_rate_limit_errors_total.labels(error_type="ConnectionError").inc()
        redis_lua_script_executions_total.labels(script_name="sliding_window", status="error").inc()

        # Verify error metrics recorded
        assert redis_rate_limit_errors_total.labels(error_type="ConnectionError")._value.get() >= 1
        assert (
            redis_lua_script_executions_total.labels(
                script_name="sliding_window", status="error"
            )._value.get()
            >= 1
        )

    def test_connection_pool_metrics_update(self):
        """Test connection pool metrics can be updated."""
        # Simulate connection pool state
        redis_connection_pool_size_current.set(100)
        redis_connection_pool_available_current.set(75)

        # Verify pool metrics
        assert redis_connection_pool_size_current._value.get() == 100
        assert redis_connection_pool_available_current._value.get() == 75

        # Calculate utilization (for verification)
        pool_size = redis_connection_pool_size_current._value.get()
        available = redis_connection_pool_available_current._value.get()
        utilization = 100 * (1 - (available / pool_size))

        # Utilization should be 25%
        assert utilization == 25.0

    def test_sliding_window_size_tracking(self):
        """Test sliding window size gauge updates."""
        key_prefix = "test_window_tracking"

        # Simulate window size changes
        redis_sliding_window_requests_current.labels(key_prefix=key_prefix).set(0)
        assert redis_sliding_window_requests_current.labels(key_prefix=key_prefix)._value.get() == 0

        # Window grows as requests arrive
        redis_sliding_window_requests_current.labels(key_prefix=key_prefix).set(10)
        assert (
            redis_sliding_window_requests_current.labels(key_prefix=key_prefix)._value.get() == 10
        )

        # Window shrinks as old requests expire
        redis_sliding_window_requests_current.labels(key_prefix=key_prefix).set(5)
        assert redis_sliding_window_requests_current.labels(key_prefix=key_prefix)._value.get() == 5


class TestMetricsCardinality:
    """Tests for metrics cardinality management (prevent label explosion)."""

    def test_extract_key_prefix_reduces_cardinality(self):
        """Test that extract_key_prefix reduces cardinality by removing IDs."""
        # 1000 unique user keys
        user_keys = [f"user:{i}:contacts_search" for i in range(1000)]

        # Extract prefixes
        prefixes = [extract_key_prefix(key) for key in user_keys]

        # All should map to same prefix (cardinality: 1000 → 1)
        assert len(set(prefixes)) == 1
        assert prefixes[0] == "user_contacts_search"

    def test_extract_key_prefix_preserves_semantic_differences(self):
        """Test that extract_key_prefix preserves semantic differences."""
        keys = [
            "user:123:contacts_search",
            "user:123:contacts_update",
            "user:123:emails_send",
            "api:gmail:send",
            "api:calendar:read",
        ]

        prefixes = [extract_key_prefix(key) for key in keys]

        # Each semantic pattern should have unique prefix
        unique_prefixes = set(prefixes)
        assert len(unique_prefixes) == 5
        assert "user_contacts_search" in unique_prefixes
        assert "user_contacts_update" in unique_prefixes
        assert "user_emails_send" in unique_prefixes
        assert "api_gmail_send" in unique_prefixes
        assert "api_calendar_read" in unique_prefixes

    def test_metrics_use_key_prefix_not_full_key(self):
        """Test that metrics use key_prefix label (not full key) to avoid cardinality explosion."""
        # Simulate 100 users hitting same endpoint
        for user_id in range(100):
            key = f"user:{user_id}:contacts_search"
            prefix = extract_key_prefix(key)

            # All should use same prefix
            redis_rate_limit_allows_total.labels(key_prefix=prefix).inc()

        # Only ONE label value should exist (not 100)
        # Verify by checking metric registry
        metric = redis_rate_limit_allows_total.labels(key_prefix="user_contacts_search")
        assert metric._value.get() >= 100  # All 100 increments on same label
