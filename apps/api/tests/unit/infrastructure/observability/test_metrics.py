"""
Unit tests for Prometheus metrics module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 22
Created: 2025-11-20
Updated: 2026-07 (F27) — endpoint labels use the matched ROUTE TEMPLATE
(cardinality-bounded), and update_db_pool_metrics no longer runs per request
(it moved to the lifetime-metrics background updater). 2026-10 (lot 9 review):
the in-progress gauge, labelled before routing, takes the template routing
will pick instead of the path with its identifiers collapsed.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.observability.metrics import (
    PrometheusMiddleware,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    metrics_endpoint,
)


def _make_request(path: str = "/api/test") -> Mock:
    """Mock Starlette request of an app serving nothing (routing matches no route)."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.url.path = path
    request.scope = {"type": "http", "method": "GET", "path": path}
    request.app = Starlette()
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
        """A request no route serves is gauged as unmatched (labelled before routing)."""
        call_next = AsyncMock(return_value=mock_response)

        with patch.object(http_requests_in_progress, "labels") as mock_labels:
            mock_metric = Mock()
            mock_labels.return_value = mock_metric

            await middleware.dispatch(mock_request, call_next)

            mock_labels.assert_called_with(method="GET", endpoint="unmatched")
            mock_metric.inc.assert_called_once()
            mock_metric.dec.assert_called_once()

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
                call.kwargs.get("endpoint") == "unmatched" for call in mock_labels.call_args_list
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

    @domain.get("/{space_id}/in-progress")
    async def in_progress(space_id: str) -> float | None:
        # Read WHILE the request runs: the gauge counts it under its label.
        labels = {"method": "GET", "endpoint": "/api/v1/spaces/{space_id}/in-progress"}
        return REGISTRY.get_sample_value("http_requests_in_progress", labels)

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


def _gauged_endpoints() -> set[str]:
    """Every endpoint label the in-progress gauge has ever been given."""
    return {
        sample.labels["endpoint"]
        for metric in REGISTRY.collect()
        if metric.name == "http_requests_in_progress"
        for sample in metric.samples
    }


class TestInProgressGauge:
    """The in-progress gauge is labelled BEFORE routing, with the template
    routing will pick — never the path. Labelled with the path, identifier
    segments collapsed, ``/relations/{name}`` kept a person's name in the
    label for the worker's life, and every bot scan opened a series of its own.
    """

    def test_a_request_is_counted_under_its_template_while_it_runs(self) -> None:
        response = TestClient(_nested_app()).get("/api/v1/spaces/Jane%20Doe/in-progress")

        assert response.json() == 1.0
        assert not any("Jane" in endpoint for endpoint in _gauged_endpoints())

    def test_a_scan_is_counted_as_unmatched(self) -> None:
        TestClient(_nested_app()).get("/wp-admin/install.php")

        assert "unmatched" in _gauged_endpoints()
        assert "/wp-admin/install.php" not in _gauged_endpoints()

    def test_a_wrong_method_is_counted_under_the_route_that_refuses_it(self) -> None:
        # Routing's own rule: no full match, so the first partial one — a 405
        # answered under that route.
        client = TestClient(_nested_app())
        assert client.post("/api/v1/spaces/Jane%20Doe/documents").status_code == 405

        labels = {"method": "POST", "endpoint": "/api/v1/spaces/{space_id}/documents"}
        assert REGISTRY.get_sample_value("http_requests_in_progress", labels) == 0.0

    def test_a_failing_request_releases_the_label_it_took(self) -> None:
        client = TestClient(_nested_app(), raise_server_exceptions=False)
        assert client.get("/api/v1/spaces/broken").status_code == 500

        labels = {"method": "GET", "endpoint": "/api/v1/spaces/broken"}
        assert REGISTRY.get_sample_value("http_requests_in_progress", labels) == 0.0


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
