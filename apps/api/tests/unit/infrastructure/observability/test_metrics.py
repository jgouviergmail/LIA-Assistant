"""
Unit tests for Prometheus metrics module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 22
Created: 2025-11-20
Target: 68% → 80%+ coverage
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.observability.metrics import (
    PrometheusMiddleware,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    metrics_endpoint,
)


@pytest.fixture
def mock_request():
    """Create a mock Starlette request."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.url.path = "/api/test"
    return request


@pytest.fixture
def mock_response():
    """Create a mock response."""
    response = Mock(spec=Response)
    response.status_code = 200
    return response


@pytest.fixture
def middleware():
    """Create PrometheusMiddleware instance."""
    app = Mock()
    return PrometheusMiddleware(app)


class TestPrometheusMiddleware:
    """Tests for PrometheusMiddleware HTTP metrics collection."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_metrics_endpoint(self, middleware, mock_request):
        """Test that /metrics endpoint is skipped from metrics collection (Lines 268-269)."""
        # Setup: /metrics endpoint
        mock_request.url.path = "/metrics"
        mock_response = Mock(spec=Response)

        # Mock call_next
        call_next = AsyncMock(return_value=mock_response)

        # Lines 268-269 executed: Skip /metrics endpoint
        response = await middleware.dispatch(mock_request, call_next)

        # Should pass through without metrics
        assert response == mock_response
        call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_increments_requests_in_progress(
        self, middleware, mock_request, mock_response
    ):
        """Test that requests in progress gauge is incremented (Line 275)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock Prometheus gauge
        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_metric.inc = Mock()
            mock_metric.dec = Mock()
            mock_labels.return_value = mock_metric

            # Line 275 executed: http_requests_in_progress.inc()
            await middleware.dispatch(mock_request, call_next)

            # Verify increment called with correct labels
            mock_labels.assert_called_with(method="GET", endpoint="/api/test")
            mock_metric.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_records_request_duration(self, middleware, mock_request, mock_response):
        """Test that request duration is recorded in histogram (Lines 279-283)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock Prometheus histogram
        with patch.object(http_request_duration_seconds, "labels") as mock_labels:
            mock_metric = Mock()
            mock_timer = Mock()
            mock_timer.__enter__ = Mock(return_value=mock_timer)
            mock_timer.__exit__ = Mock(return_value=None)
            mock_metric.time = Mock(return_value=mock_timer)
            mock_labels.return_value = mock_metric

            # Lines 279-283 executed: Duration histogram context manager
            await middleware.dispatch(mock_request, call_next)

            # Verify timer context manager used
            mock_labels.assert_called_with(method="GET", endpoint="/api/test")
            mock_metric.time.assert_called_once()
            mock_timer.__enter__.assert_called_once()
            mock_timer.__exit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_increments_requests_total(
        self, middleware, mock_request, mock_response
    ):
        """Test that total requests counter is incremented (Lines 286-290)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock Prometheus counter
        with patch.object(http_requests_total, "labels") as mock_labels:
            mock_metric = Mock()
            mock_metric.inc = Mock()
            mock_labels.return_value = mock_metric

            # Lines 286-290 executed: http_requests_total.inc()
            await middleware.dispatch(mock_request, call_next)

            # Verify counter incremented with status code
            mock_labels.assert_called_with(method="GET", endpoint="/api/test", status=200)
            mock_metric.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_updates_db_pool_metrics(self, middleware, mock_request, mock_response):
        """Test that DB pool metrics are updated (Lines 294-297)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock update_db_pool_metrics function (imported locally in dispatch)
        mock_update = Mock()

        with patch("src.infrastructure.database.session.update_db_pool_metrics", mock_update):
            # Lines 294-297 executed: Import and call update_db_pool_metrics
            await middleware.dispatch(mock_request, call_next)

            # Verify DB metrics update called
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_handles_db_metrics_error_gracefully(
        self, middleware, mock_request, mock_response, caplog
    ):
        """Test that DB metrics update errors don't fail request (Lines 298-300)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock update_db_pool_metrics to raise exception
        mock_update = Mock(side_effect=RuntimeError("DB metrics error"))

        with patch("src.infrastructure.database.session.update_db_pool_metrics", mock_update):
            # Lines 298-300 executed: Exception caught, logged, request continues
            response = await middleware.dispatch(mock_request, call_next)

            # Request should succeed despite metrics error
            assert response == mock_response
            call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_returns_response(self, middleware, mock_request, mock_response):
        """Test that response is returned correctly (Line 302)."""
        call_next = AsyncMock(return_value=mock_response)

        # Line 302 executed: return response
        response = await middleware.dispatch(mock_request, call_next)

        assert response == mock_response

    @pytest.mark.asyncio
    async def test_dispatch_decrements_in_progress_in_finally(
        self, middleware, mock_request, mock_response
    ):
        """Test that in-progress gauge is decremented in finally block (Line 306)."""
        call_next = AsyncMock(return_value=mock_response)

        # Mock Prometheus gauge
        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_metric.inc = Mock()
            mock_metric.dec = Mock()
            mock_labels.return_value = mock_metric

            # Line 306 executed: finally block dec()
            await middleware.dispatch(mock_request, call_next)

            # Verify decrement called (cleanup)
            mock_metric.dec.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_decrements_in_progress_on_exception(self, middleware, mock_request):
        """Test that in-progress gauge is decremented even when exception raised (Line 306)."""
        # Mock call_next to raise exception
        call_next = AsyncMock(side_effect=RuntimeError("Request failed"))

        # Mock Prometheus gauge
        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_metric.inc = Mock()
            mock_metric.dec = Mock()
            mock_labels.return_value = mock_metric

            # Line 306 executed: finally block ensures dec() even on exception
            with pytest.raises(RuntimeError):
                await middleware.dispatch(mock_request, call_next)

            # Verify decrement called despite exception
            mock_metric.dec.assert_called_once()


class TestMetricsEndpoint:
    """Tests for Prometheus metrics HTTP endpoint."""

    def test_metrics_endpoint_generates_prometheus_format(self):
        """Test that metrics endpoint generates Prometheus format (Lines 316-317)."""
        # Mock generate_latest to return fake metrics
        fake_metrics = b'# HELP http_requests_total Total HTTP requests\n# TYPE http_requests_total counter\nhttp_requests_total{method="GET",endpoint="/api/test",status="200"} 42\n'

        with patch(
            "src.infrastructure.observability.metrics.generate_latest", return_value=fake_metrics
        ):
            # Lines 316-317 executed: generate_latest() called
            response = metrics_endpoint()

            # Verify response contains metrics data
            assert response.body == fake_metrics

    def test_metrics_endpoint_returns_correct_content_type(self):
        """Test that metrics endpoint returns correct Prometheus content-type (Lines 318-320)."""
        fake_metrics = b"# Metrics\n"

        with patch(
            "src.infrastructure.observability.metrics.generate_latest", return_value=fake_metrics
        ):
            # Lines 318-320 executed: Response with correct media_type
            response = metrics_endpoint()

            # Verify Prometheus content-type
            assert response.media_type == "text/plain; version=0.0.4; charset=utf-8"

    def test_metrics_endpoint_returns_response_object(self):
        """Test that metrics endpoint returns Starlette Response object."""
        fake_metrics = b"# Metrics\n"

        with patch(
            "src.infrastructure.observability.metrics.generate_latest", return_value=fake_metrics
        ):
            response = metrics_endpoint()

            # Verify response type
            assert isinstance(response, Response)
