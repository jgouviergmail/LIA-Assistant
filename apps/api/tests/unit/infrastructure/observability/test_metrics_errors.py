"""
Tests for error taxonomy metrics (metrics_errors.py).

Tests all Prometheus Counter metrics for errors:
- HTTP errors (4xx/5xx)
- LLM API errors
- External service errors
- Validation errors
- Security violations

Target: 100% coverage of metrics_errors.py
"""

from src.infrastructure.observability.metrics_errors import (
    # External Service Error Metrics
    external_service_errors_total,
    external_service_timeouts_total,
    http_client_errors_total,
    # HTTP Error Metrics
    http_errors_total,
    http_server_errors_total,
    # LLM API Error Metrics
    llm_api_errors_total,
    llm_content_filter_violations_total,
    llm_context_length_exceeded_total,
    llm_rate_limit_hit_total,
    # Security Error Metrics
    security_violations_total,
    # Validation Error Metrics
    validation_errors_total,
)


class TestHTTPErrorMetrics:
    """Test HTTP error metrics (4xx and 5xx)."""

    def test_http_errors_total_metric_exists(self):
        """Test http_errors_total metric is registered."""
        assert http_errors_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert http_errors_total._name == "http_errors"
        assert http_errors_total._type == "counter"

    def test_http_errors_total_labels(self):
        """Test http_errors_total has correct labels."""
        # Labels: status_code, exception_type, endpoint
        http_errors_total.labels(
            status_code="404", exception_type="NotFoundError", endpoint="/api/v1/users"
        ).inc()

        metric_value = http_errors_total.labels(
            status_code="404", exception_type="NotFoundError", endpoint="/api/v1/users"
        )._value._value

        assert metric_value >= 1

    def test_http_client_errors_total_metric_exists(self):
        """Test http_client_errors_total metric (4xx errors)."""
        assert http_client_errors_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert http_client_errors_total._name == "http_client_errors"

    def test_http_client_errors_total_labels(self):
        """Test http_client_errors_total with error types."""
        # Test authentication_failed
        http_client_errors_total.labels(error_type="authentication_failed").inc()

        # Test authorization_failed
        http_client_errors_total.labels(error_type="authorization_failed").inc()

        # Test validation_failed
        http_client_errors_total.labels(error_type="validation_failed").inc()

        # Test resource_not_found
        http_client_errors_total.labels(error_type="resource_not_found").inc()

        # Test resource_conflict
        http_client_errors_total.labels(error_type="resource_conflict").inc()

        # Test rate_limit_exceeded
        http_client_errors_total.labels(error_type="rate_limit_exceeded").inc()

        # Verify all labels work
        assert (
            http_client_errors_total.labels(error_type="authentication_failed")._value._value >= 1
        )

    def test_http_server_errors_total_metric_exists(self):
        """Test http_server_errors_total metric (5xx errors)."""
        assert http_server_errors_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert http_server_errors_total._name == "http_server_errors"

    def test_http_server_errors_total_labels(self):
        """Test http_server_errors_total with error types."""
        # Test internal_server_error
        http_server_errors_total.labels(error_type="internal_server_error").inc()

        # Test database_error
        http_server_errors_total.labels(error_type="database_error").inc()

        # Test external_service_error
        http_server_errors_total.labels(error_type="external_service_error").inc()

        # Test llm_service_error
        http_server_errors_total.labels(error_type="llm_service_error").inc()

        # Test timeout_error
        http_server_errors_total.labels(error_type="timeout_error").inc()

        assert (
            http_server_errors_total.labels(error_type="internal_server_error")._value._value >= 1
        )


class TestLLMAPIErrorMetrics:
    """Test LLM API error metrics."""

    def test_llm_api_errors_total_metric_exists(self):
        """Test llm_api_errors_total metric is registered."""
        assert llm_api_errors_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert llm_api_errors_total._name == "llm_api_errors"

    def test_llm_api_errors_total_labels(self):
        """Test llm_api_errors_total with providers and error types."""
        # Test OpenAI rate limit
        llm_api_errors_total.labels(provider="openai", error_type="rate_limit").inc()

        # Test Anthropic timeout
        llm_api_errors_total.labels(provider="anthropic", error_type="timeout").inc()

        # Test Google invalid request
        llm_api_errors_total.labels(provider="google", error_type="invalid_request").inc()

        # Test context length exceeded
        llm_api_errors_total.labels(provider="openai", error_type="context_length_exceeded").inc()

        # Test authentication error
        llm_api_errors_total.labels(provider="anthropic", error_type="authentication").inc()

        # Test content filter
        llm_api_errors_total.labels(provider="openai", error_type="content_filter").inc()

        # Test model not found
        llm_api_errors_total.labels(provider="google", error_type="model_not_found").inc()

        assert (
            llm_api_errors_total.labels(provider="openai", error_type="rate_limit")._value._value
            >= 1
        )

    def test_llm_rate_limit_hit_total_metric_exists(self):
        """Test llm_rate_limit_hit_total metric."""
        assert llm_rate_limit_hit_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert llm_rate_limit_hit_total._name == "llm_rate_limit_hit"

    def test_llm_rate_limit_hit_total_labels(self):
        """Test llm_rate_limit_hit_total with limit types."""
        # Test requests per minute
        llm_rate_limit_hit_total.labels(provider="openai", limit_type="requests_per_minute").inc()

        # Test tokens per minute
        llm_rate_limit_hit_total.labels(provider="anthropic", limit_type="tokens_per_minute").inc()

        # Test requests per day
        llm_rate_limit_hit_total.labels(provider="google", limit_type="requests_per_day").inc()

        assert (
            llm_rate_limit_hit_total.labels(
                provider="openai", limit_type="requests_per_minute"
            )._value._value
            >= 1
        )

    def test_llm_context_length_exceeded_total_metric_exists(self):
        """Test llm_context_length_exceeded_total metric."""
        assert llm_context_length_exceeded_total is not None
        # Prometheus automatically strips '_total' suffix from Counter names
        assert llm_context_length_exceeded_total._name == "llm_context_length_exceeded"

    def test_llm_context_length_exceeded_total_labels(self):
        """Test llm_context_length_exceeded_total with models."""
        # Test GPT-4
        llm_context_length_exceeded_total.labels(provider="openai", model="gpt-4").inc()

        # Test gpt-4.1-mini-mini
        llm_context_length_exceeded_total.labels(provider="openai", model="gpt-4.1-mini-mini").inc()

        # Test Claude 3.5 Sonnet
        llm_context_length_exceeded_total.labels(
            provider="anthropic", model="claude-3-5-sonnet"
        ).inc()

        assert (
            llm_context_length_exceeded_total.labels(provider="openai", model="gpt-4")._value._value
            >= 1
        )

    def test_llm_content_filter_violations_total_metric_exists(self):
        """Test llm_content_filter_violations_total metric."""
        assert llm_content_filter_violations_total is not None
        # Prometheus Counter _name doesn't include _total suffix (added on export)
        assert llm_content_filter_violations_total._name == "llm_content_filter_violations"

    def test_llm_content_filter_violations_total_labels(self):
        """Test llm_content_filter_violations_total with providers."""
        # Test OpenAI content filter
        llm_content_filter_violations_total.labels(provider="openai").inc()

        # Test Anthropic content filter
        llm_content_filter_violations_total.labels(provider="anthropic").inc()

        # Test Google content filter
        llm_content_filter_violations_total.labels(provider="google").inc()

        assert llm_content_filter_violations_total.labels(provider="openai")._value._value >= 1


class TestExternalServiceErrorMetrics:
    """Test external service error metrics."""

    def test_external_service_errors_total_metric_exists(self):
        """Test external_service_errors_total metric."""
        assert external_service_errors_total is not None
        # Prometheus Counter _name doesn't include _total suffix (added on export)
        assert external_service_errors_total._name == "external_service_errors"

    def test_external_service_errors_total_labels(self):
        """Test external_service_errors_total with services and error types."""
        # Test Google API errors
        external_service_errors_total.labels(
            service_name="google_api", error_type="api_error"
        ).inc()

        # Test Google People API
        external_service_errors_total.labels(
            service_name="google_people", error_type="unauthorized"
        ).inc()

        # Test Google OAuth
        external_service_errors_total.labels(
            service_name="google_oauth", error_type="timeout"
        ).inc()

        # Test Currency API
        external_service_errors_total.labels(
            service_name="currency_api", error_type="rate_limit"
        ).inc()

        # Test not found errors
        external_service_errors_total.labels(
            service_name="google_api", error_type="not_found"
        ).inc()

        assert (
            external_service_errors_total.labels(
                service_name="google_api", error_type="api_error"
            )._value._value
            >= 1
        )

    def test_external_service_timeouts_total_metric_exists(self):
        """Test external_service_timeouts_total metric."""
        assert external_service_timeouts_total is not None
        # Prometheus Counter _name doesn't include _total suffix (added on export)
        assert external_service_timeouts_total._name == "external_service_timeouts"

    def test_external_service_timeouts_total_labels(self):
        """Test external_service_timeouts_total with services."""
        # Test various service timeouts
        external_service_timeouts_total.labels(service_name="google_api").inc()
        external_service_timeouts_total.labels(service_name="google_people").inc()
        external_service_timeouts_total.labels(service_name="google_oauth").inc()
        external_service_timeouts_total.labels(service_name="currency_api").inc()

        assert external_service_timeouts_total.labels(service_name="google_api")._value._value >= 1


class TestValidationErrorMetrics:
    """Test validation error metrics."""

    def test_validation_errors_total_metric_exists(self):
        """Test validation_errors_total metric."""
        assert validation_errors_total is not None
        # Prometheus Counter _name doesn't include _total suffix (added on export)
        assert validation_errors_total._name == "validation_errors"

    def test_validation_errors_total_labels(self):
        """Test validation_errors_total with fields and error types."""
        # Test email validation
        validation_errors_total.labels(field="email", error_type="invalid_format").inc()

        # Test password validation
        validation_errors_total.labels(field="password", error_type="too_short").inc()

        # Test connector_type validation
        validation_errors_total.labels(field="connector_type", error_type="invalid_choice").inc()

        # Test message validation
        validation_errors_total.labels(field="message", error_type="too_long").inc()

        # Test missing field
        validation_errors_total.labels(field="user_id", error_type="missing").inc()

        assert (
            validation_errors_total.labels(field="email", error_type="invalid_format")._value._value
            >= 1
        )


class TestSecurityErrorMetrics:
    """Test security error metrics."""

    def test_security_violations_total_metric_exists(self):
        """Test security_violations_total metric."""
        assert security_violations_total is not None
        # Prometheus Counter _name doesn't include _total suffix (added on export)
        assert security_violations_total._name == "security_violations"

    def test_security_violations_total_labels(self):
        """Test security_violations_total with violation types."""
        # Test CSRF token mismatch
        security_violations_total.labels(violation_type="csrf_token_mismatch").inc()

        # Test OAuth state mismatch
        security_violations_total.labels(violation_type="oauth_state_mismatch").inc()

        # Test PKCE failed
        security_violations_total.labels(violation_type="pkce_failed").inc()

        # Test invalid session
        security_violations_total.labels(violation_type="invalid_session").inc()

        # Test expired token
        security_violations_total.labels(violation_type="expired_token").inc()

        # Test unauthorized access
        security_violations_total.labels(violation_type="unauthorized_access").inc()

        assert (
            security_violations_total.labels(violation_type="csrf_token_mismatch")._value._value
            >= 1
        )


class TestMetricsIntegration:
    """Test metrics integration and real-world scenarios."""

    def test_all_metrics_are_registered(self):
        """Test all error metrics are properly defined and can be used."""
        # Verify metrics are valid Counter instances with correct names
        # (REGISTRY.collect() only shows metrics that have been used)

        # HTTP error metrics
        assert http_errors_total._name == "http_errors"
        assert http_client_errors_total._name == "http_client_errors"
        assert http_server_errors_total._name == "http_server_errors"

        # LLM API error metrics
        assert llm_api_errors_total._name == "llm_api_errors"
        assert llm_rate_limit_hit_total._name == "llm_rate_limit_hit"
        assert llm_context_length_exceeded_total._name == "llm_context_length_exceeded"
        assert llm_content_filter_violations_total._name == "llm_content_filter_violations"

        # External service error metrics
        assert external_service_errors_total._name == "external_service_errors"
        assert external_service_timeouts_total._name == "external_service_timeouts"

        # Validation error metrics
        assert validation_errors_total._name == "validation_errors"

        # Security error metrics
        assert security_violations_total._name == "security_violations"

    def test_simulate_http_error_flow(self):
        """Test simulating HTTP error flow (404 Not Found)."""
        # Simulate 404 error
        http_errors_total.labels(
            status_code="404",
            exception_type="ResourceNotFoundError",
            endpoint="/api/v1/conversations/123",
        ).inc()

        http_client_errors_total.labels(error_type="resource_not_found").inc()

        # Verify both metrics incremented
        assert (
            http_errors_total.labels(
                status_code="404",
                exception_type="ResourceNotFoundError",
                endpoint="/api/v1/conversations/123",
            )._value._value
            >= 1
        )
        assert http_client_errors_total.labels(error_type="resource_not_found")._value._value >= 1

    def test_simulate_llm_rate_limit_flow(self):
        """Test simulating LLM rate limit hit."""
        # Simulate OpenAI rate limit
        llm_api_errors_total.labels(provider="openai", error_type="rate_limit").inc()
        llm_rate_limit_hit_total.labels(provider="openai", limit_type="tokens_per_minute").inc()

        # Verify both metrics incremented
        assert (
            llm_api_errors_total.labels(provider="openai", error_type="rate_limit")._value._value
            >= 1
        )
        assert (
            llm_rate_limit_hit_total.labels(
                provider="openai", limit_type="tokens_per_minute"
            )._value._value
            >= 1
        )

    def test_simulate_security_violation_flow(self):
        """Test simulating security violation (OAuth attack)."""
        # Simulate OAuth state mismatch (potential CSRF attack)
        security_violations_total.labels(violation_type="oauth_state_mismatch").inc()
        http_client_errors_total.labels(error_type="authentication_failed").inc()

        # Verify both metrics incremented
        assert (
            security_violations_total.labels(violation_type="oauth_state_mismatch")._value._value
            >= 1
        )
        assert (
            http_client_errors_total.labels(error_type="authentication_failed")._value._value >= 1
        )

    def test_metric_increment_by_value(self):
        """Test incrementing metrics by specific values."""
        initial_value = http_errors_total.labels(
            status_code="500", exception_type="DatabaseError", endpoint="/api/v1/chat"
        )._value._value

        # Increment by 5 (e.g., batch error reporting)
        http_errors_total.labels(
            status_code="500", exception_type="DatabaseError", endpoint="/api/v1/chat"
        ).inc(5)

        final_value = http_errors_total.labels(
            status_code="500", exception_type="DatabaseError", endpoint="/api/v1/chat"
        )._value._value

        assert final_value == initial_value + 5
