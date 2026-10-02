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

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
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


def _make_request(path: str = "/api/test") -> Mock:
    """Mock Starlette request that routing never reached (no route in its scope)."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.url.path = path
    request.scope = {}
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


def _nested_app(*, served_twice: bool = False) -> FastAPI:
    """LIA's shape: a domain router with its own prefix, included under /api/v1."""
    domain = APIRouter(prefix="/spaces")

    @domain.get("/{space_id}/documents")
    async def documents(space_id: str) -> dict[str, str]:
        return {"space": space_id}

    @domain.get("/broken")
    async def broken() -> None:
        raise RuntimeError("endpoint failure")

    api_router = APIRouter()
    api_router.include_router(domain)
    if served_twice:
        api_router.include_router(domain, prefix="/mirror")
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.add_middleware(PrometheusMiddleware)
    return app


def _requests(endpoint: str, status: int) -> float:
    labels = {"method": "GET", "endpoint": endpoint, "status": str(status)}
    return REGISTRY.get_sample_value("http_requests_total", labels) or 0.0


def _durations(endpoint: str) -> float:
    labels = {"method": "GET", "endpoint": endpoint}
    return REGISTRY.get_sample_value("http_request_duration_seconds_count", labels) or 0.0


class TestServedRouteTemplate:
    """The endpoint label is the template the request was SERVED under.

    FastAPI 0.137+ hands the request scope the ORIGINAL route of an included
    router, whose path misses every including router's prefix — measured on
    0.141.1, ``/rag-spaces/{space_id}/documents`` where 0.136.3 labelled
    ``/api/v1/rag-spaces/{space_id}/documents``. Only a real app routes.
    """

    def test_a_routed_request_carries_every_prefix(self) -> None:
        template = "/api/v1/spaces/{space_id}/documents"
        before = _requests(template, 200)
        prefixless = _requests("/spaces/{space_id}/documents", 200)

        TestClient(_nested_app()).get("/api/v1/spaces/7/documents")

        assert _requests(template, 200) == before + 1
        assert _requests("/spaces/{space_id}/documents", 200) == prefixless

    def test_a_failing_endpoint_is_timed_under_its_template(self) -> None:
        before = _durations("/api/v1/spaces/broken")

        client = TestClient(_nested_app(), raise_server_exceptions=False)
        assert client.get("/api/v1/spaces/broken").status_code == 500

        assert _durations("/api/v1/spaces/broken") == before + 1

    def test_an_unrouted_request_is_unmatched(self) -> None:
        before = _requests("unmatched", 404)

        TestClient(_nested_app()).get("/api/v1/nowhere/at/all")

        assert _requests("unmatched", 404) == before + 1

    def test_a_route_served_twice_keeps_its_own_path_rather_than_a_guess(self) -> None:
        # One route object under two templates: the scope cannot say which one
        # matched, so neither is claimed.
        own = "/spaces/{space_id}/documents"
        before = _requests(own, 200)

        TestClient(_nested_app(served_twice=True)).get("/api/v1/mirror/spaces/7/documents")

        assert _requests(own, 200) == before + 1


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
