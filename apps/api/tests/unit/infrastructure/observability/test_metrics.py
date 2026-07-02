"""
Unit tests for Prometheus metrics module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 22
Created: 2025-11-20
Updated: 2026-07 (F27) — endpoint labels use the matched ROUTE TEMPLATE
(cardinality-bounded) with an id-collapsing fallback for the in-progress
gauge, and update_db_pool_metrics no longer runs per request (it moved to
the lifetime-metrics background updater).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.observability.metrics import (
    PrometheusMiddleware,
    _normalize_path_fallback,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    metrics_endpoint,
)


def _make_request(path: str = "/api/test", route_path: str | None = None) -> Mock:
    """Mock Starlette request; route_path simulates the post-routing template."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.url.path = path
    request.scope = {"route": SimpleNamespace(path=route_path)} if route_path else {}
    return request


@pytest.fixture
def mock_request():
    """Create a mock Starlette request (unrouted → 'unmatched' label)."""
    return _make_request()


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


class TestNormalizePathFallback:
    """Cardinality guard for labels captured BEFORE routing (F27)."""

    def test_uuid_segment_collapsed(self):
        assert (
            _normalize_path_fallback("/api/v1/journals/9b2e4c1a-1234-4f5e-8a9b-0c1d2e3f4a5b")
            == "/api/v1/journals/{id}"
        )

    def test_numeric_segment_collapsed(self):
        assert (
            _normalize_path_fallback("/api/v1/items/12345/sub/9") == "/api/v1/items/{id}/sub/{id}"
        )

    def test_long_hex_segment_collapsed(self):
        assert _normalize_path_fallback("/files/5f2b1c9e8d7a6b5c4d3e2f1a0b9c8d7e") == "/files/{id}"

    def test_plain_path_unchanged(self):
        assert (
            _normalize_path_fallback("/api/v1/agents/chat/stream") == "/api/v1/agents/chat/stream"
        )


class TestPrometheusMiddleware:
    """Tests for PrometheusMiddleware HTTP metrics collection (F27 contract)."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_metrics_endpoint(self, middleware, mock_request):
        """/metrics endpoint is excluded from metrics collection."""
        mock_request.url.path = "/metrics"
        mock_response = Mock(spec=Response)
        call_next = AsyncMock(return_value=mock_response)

        response = await middleware.dispatch(mock_request, call_next)

        assert response == mock_response
        call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_increments_requests_in_progress(
        self, middleware, mock_request, mock_response
    ):
        """In-progress gauge uses the normalized-path fallback (pre-routing)."""
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            await middleware.dispatch(mock_request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="/api/test")
            mock_metric.inc.assert_called_once()
            mock_metric.dec.assert_called_once()

    @pytest.mark.asyncio
    async def test_in_progress_label_collapses_ids(self, middleware, mock_response):
        """UUID path segments never reach the in-progress label raw."""
        request = _make_request(path="/api/v1/journals/9b2e4c1a-1234-4f5e-8a9b-0c1d2e3f4a5b")
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_labels.return_value = Mock()
            await middleware.dispatch(request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="/api/v1/journals/{id}")

    @pytest.mark.asyncio
    async def test_dispatch_records_request_duration_with_route_template(
        self, middleware, mock_response
    ):
        """Duration histogram uses the matched route template (post-routing)."""
        request = _make_request(
            path="/api/v1/journals/9b2e4c1a-1234-4f5e-8a9b-0c1d2e3f4a5b",
            route_path="/api/v1/journals/{entry_id}",
        )
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_request_duration_seconds, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            await middleware.dispatch(request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="/api/v1/journals/{entry_id}")
            mock_metric.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_records_duration_on_exception(self, middleware, mock_request):
        """Duration is observed even when the endpoint raises (parity with the
        historical `with histogram.time():` context manager)."""
        call_next = AsyncMock(side_effect=RuntimeError("Request failed"))

        with patch.object(http_request_duration_seconds, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            with pytest.raises(RuntimeError):
                await middleware.dispatch(mock_request, call_next)

            mock_metric.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_increments_requests_total_unmatched(
        self, middleware, mock_request, mock_response
    ):
        """Unrouted requests (404s, bot scans) collapse into 'unmatched'."""
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_requests_total, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            await middleware.dispatch(mock_request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="unmatched", status=200)
            mock_metric.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_increments_requests_total_with_route(self, middleware, mock_response):
        """Routed requests use the exact route template."""
        request = _make_request(path="/api/v1/health", route_path="/api/v1/health")
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_requests_total, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            await middleware.dispatch(request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="/api/v1/health", status=200)

    @pytest.mark.asyncio
    async def test_dispatch_does_not_update_db_pool_metrics(
        self, middleware, mock_request, mock_response
    ):
        """F27: DB pool metrics moved to the periodic lifetime-metrics updater —
        they must NOT run on the request path anymore."""
        call_next = AsyncMock(return_value=mock_response)
        mock_update = Mock()

        with patch("src.infrastructure.database.session.update_db_pool_metrics", mock_update):
            await middleware.dispatch(mock_request, call_next)

            mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_returns_response(self, middleware, mock_request, mock_response):
        """Response is returned unchanged."""
        call_next = AsyncMock(return_value=mock_response)

        response = await middleware.dispatch(mock_request, call_next)

        assert response == mock_response

    @pytest.mark.asyncio
    async def test_dispatch_decrements_in_progress_on_exception(self, middleware, mock_request):
        """In-progress gauge decremented (same label) even on exception."""
        call_next = AsyncMock(side_effect=RuntimeError("Request failed"))

        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            with pytest.raises(RuntimeError):
                await middleware.dispatch(mock_request, call_next)

            mock_metric.dec.assert_called_once()
            # inc and dec must target the SAME label value
            assert all(
                call.kwargs.get("endpoint") == "/api/test" for call in mock_labels.call_args_list
            )


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
