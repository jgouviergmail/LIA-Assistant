"""
Unit tests for core/middleware.py (pure-ASGI versions — F28).

The middleware stack was converted from BaseHTTPMiddleware to pure ASGI;
these tests exercise the REAL ASGI stack through TestClient (no dispatch()
mocks) and pin the exact guarantees the historical versions provided:
request-ID generation/propagation, security headers, request/response
logging with path exclusion, structured 500s, and middleware ordering.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.middleware import (
    ErrorHandlerMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    _is_excluded,
    setup_middleware,
)


def _make_app(*middleware_classes: type) -> FastAPI:
    """FastAPI app with test routes and the given middleware (only)."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(request: Request) -> dict:
        return {
            "message": "ok",
            "request_id": getattr(request.state, "request_id", None),
        }

    @app.get("/error")
    async def error_endpoint() -> dict:
        raise ValueError("Test error")

    for cls in middleware_classes:
        app.add_middleware(cls)
    return app


# =============================================================================
# RequestIDMiddleware
# =============================================================================


@pytest.mark.unit
class TestRequestIDMiddleware:
    """Request-ID generation, reuse, propagation to routes and response."""

    def test_generates_request_id_when_not_provided(self):
        client = TestClient(_make_app(RequestIDMiddleware))
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-Request-ID"]
        # UUID4 format
        assert len(response.headers["X-Request-ID"]) == 36

    def test_reuses_incoming_request_id(self):
        client = TestClient(_make_app(RequestIDMiddleware))
        response = client.get("/test", headers={"X-Request-ID": "client-supplied-id"})

        assert response.headers["X-Request-ID"] == "client-supplied-id"

    def test_request_state_exposes_request_id_to_routes(self):
        client = TestClient(_make_app(RequestIDMiddleware))
        response = client.get("/test", headers={"X-Request-ID": "abc-123"})

        assert response.json()["request_id"] == "abc-123"

    def test_binds_structlog_contextvars(self):
        client = TestClient(_make_app(RequestIDMiddleware))
        with patch("src.core.middleware.structlog.contextvars.bind_contextvars") as mock_bind:
            client.get("/test", headers={"X-Request-ID": "ctx-1"})

        kwargs = mock_bind.call_args.kwargs
        assert kwargs["request_id"] == "ctx-1"
        assert kwargs["path"] == "/test"
        assert kwargs["method"] == "GET"


# =============================================================================
# SecurityHeadersMiddleware
# =============================================================================


@pytest.mark.unit
class TestSecurityHeadersMiddleware:
    """Security headers on every response; HSTS gated to production."""

    def test_adds_security_headers(self):
        client = TestClient(_make_app(SecurityHeadersMiddleware))
        response = client.get("/test")

        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"

    def test_csp_restricts_scripts_to_self(self):
        client = TestClient(_make_app(SecurityHeadersMiddleware))
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_hsts_only_in_production(self):
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.is_production = False
            mock_settings.hsts_max_age = 2_592_000
            client = TestClient(_make_app(SecurityHeadersMiddleware))
            response = client.get("/test")
        assert "Strict-Transport-Security" not in response.headers

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.hsts_max_age = 2_592_000
            client = TestClient(_make_app(SecurityHeadersMiddleware))
            response = client.get("/test")
        assert response.headers["Strict-Transport-Security"] == "max-age=2592000"

    def test_hsts_max_age_comes_from_settings(self):
        """The value is the configured step, not a number frozen in the code.

        SEC-025 raises HSTS in stages because a pin cannot be recalled early.
        A hardcoded max-age makes that ladder fiction — it was 31536000 here
        while the web app was serving 86400 from `HSTS_MAX_AGE`.
        """
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.hsts_max_age = 604_800
            client = TestClient(_make_app(SecurityHeadersMiddleware))
            response = client.get("/test")

        assert response.headers["Strict-Transport-Security"] == "max-age=604800"

    def test_hsts_never_claims_subdomains_or_preload(self):
        """Both directives are near-irreversible, and both were being emitted.

        `includeSubDomains` pins every subdomain — including any that is not
        durably HTTPS — and `preload` asks browsers to ship the pin with their
        binary, which takes months to undo. The project had already decided
        against both for the web app (`apps/web/src/lib/csp.ts`); the API was
        sending them anyway, and a browser honours the header on an API
        response exactly as on a document.
        """
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.hsts_max_age = 2_592_000
            client = TestClient(_make_app(SecurityHeadersMiddleware))
            response = client.get("/test")

        header = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" not in header
        assert "preload" not in header

    def test_hsts_can_be_switched_off(self):
        """`HSTS_MAX_AGE=0` is the escape hatch if a step has to be walked back."""
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.is_production = True
            mock_settings.hsts_max_age = 0
            client = TestClient(_make_app(SecurityHeadersMiddleware))
            response = client.get("/test")

        assert "Strict-Transport-Security" not in response.headers


# =============================================================================
# LoggingMiddleware
# =============================================================================


def _logging_settings() -> MagicMock:
    """Hermetic settings for LoggingMiddleware tests.

    The Taskfile exports the developer's root ``.env`` as real environment
    variables (see the F35 post-mortem): asserting on the AMBIENT
    ``http_log_level`` / ``http_log_exclude_paths`` makes tests fail on any
    machine with local overrides (e.g. HTTP_LOG_LEVEL=INFO). Pin them.
    """
    mock_settings = MagicMock()
    mock_settings.http_log_level = "DEBUG"
    mock_settings.http_log_exclude_paths = ["/metrics", "/health"]
    return mock_settings


@pytest.mark.unit
class TestLoggingMiddleware:
    """Request/response logging, GeoIP metric, exclusions, error logging."""

    def test_logs_request_started_and_completed(self):
        client = TestClient(_make_app(LoggingMiddleware))
        with (
            patch("src.core.middleware.settings", _logging_settings()),
            patch("src.core.middleware.logger") as mock_logger,
        ):
            response = client.get("/test")

        assert response.status_code == 200
        events = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert "request_started" in events
        assert "request_completed" in events

    def test_completed_log_carries_status_and_duration(self):
        client = TestClient(_make_app(LoggingMiddleware))
        with (
            patch("src.core.middleware.settings", _logging_settings()),
            patch("src.core.middleware.logger") as mock_logger,
        ):
            client.get("/test")

        completed = next(
            c for c in mock_logger.debug.call_args_list if c.args[0] == "request_completed"
        )
        assert completed.kwargs["status_code"] == 200
        assert completed.kwargs["duration_ms"] >= 0

    def test_increments_geoip_country_metric(self):
        client = TestClient(_make_app(LoggingMiddleware))
        with (
            patch("src.core.middleware.settings", _logging_settings()),
            patch("src.core.middleware.http_requests_by_country_total") as mock_metric,
        ):
            client.get("/test")

        mock_metric.labels.assert_called_once()
        mock_metric.labels.return_value.inc.assert_called_once()

    def test_excluded_path_skips_logs_and_metric(self):
        app = _make_app(LoggingMiddleware)

        @app.get("/health")
        async def health() -> dict:  # pragma: no cover - route body trivial
            return {"ok": True}

        client = TestClient(app)
        with (
            patch("src.core.middleware.settings", _logging_settings()),
            patch("src.core.middleware.logger") as mock_logger,
            patch("src.core.middleware.http_requests_by_country_total") as mock_metric,
        ):
            client.get("/health")

        events = [c.args[0] for c in mock_logger.debug.call_args_list]
        assert "request_started" not in events
        assert "request_completed" not in events
        mock_metric.labels.assert_not_called()

    def test_exception_logged_at_error_level_and_reraised(self):
        client = TestClient(_make_app(LoggingMiddleware), raise_server_exceptions=True)
        with (
            patch("src.core.middleware.settings", _logging_settings()),
            patch("src.core.middleware.logger") as mock_logger,
        ):
            with pytest.raises(ValueError, match="Test error"):
                client.get("/error")

        error_events = [c.args[0] for c in mock_logger.error.call_args_list]
        assert "request_failed" in error_events


@pytest.mark.unit
class TestPathExclusion:
    """_is_excluded — exact match, trailing slash, subpaths."""

    @pytest.mark.parametrize(
        ("path", "excluded"),
        [
            ("/metrics", True),
            ("/metrics/", True),
            ("/metrics/prometheus", True),
            ("/health", True),
            ("/healthz", False),
            ("/api/v1/agents", False),
            ("/", False),
        ],
    )
    def test_exclusion_variants(self, path: str, excluded: bool):
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.http_log_exclude_paths = ["/metrics", "/health"]
            assert _is_excluded(path) is excluded


# =============================================================================
# ErrorHandlerMiddleware
# =============================================================================


@pytest.mark.unit
class TestErrorHandlerMiddleware:
    """Structured 500s; detail gated by debug; mid-stream re-raise semantics."""

    def test_returns_structured_500(self):
        client = TestClient(
            _make_app(ErrorHandlerMiddleware, RequestIDMiddleware),
            raise_server_exceptions=False,
        )
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.debug = False
            response = client.get("/error")

        assert response.status_code == 500
        body = response.json()
        assert body["error"] == "Internal server error"
        assert body["detail"] == "An unexpected error occurred"
        assert body["request_id"]  # propagated from RequestIDMiddleware

    def test_debug_mode_exposes_exception_detail(self):
        client = TestClient(_make_app(ErrorHandlerMiddleware), raise_server_exceptions=False)
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.debug = True
            response = client.get("/error")

        assert response.json()["detail"] == "Test error"

    def test_logs_unhandled_exception(self):
        client = TestClient(_make_app(ErrorHandlerMiddleware), raise_server_exceptions=False)
        with patch("src.core.middleware.logger") as mock_logger:
            client.get("/error")

        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "unhandled_exception"

    def test_midstream_failure_reraises(self):
        """Once the response has started (streaming), a JSON 500 can no longer
        be sent — the exception must propagate (historical behaviour)."""
        from starlette.responses import StreamingResponse

        app = FastAPI()

        @app.get("/stream")
        async def stream_endpoint() -> StreamingResponse:
            async def broken_stream():
                yield b"first chunk"
                raise RuntimeError("mid-stream failure")

            return StreamingResponse(broken_stream())

        app.add_middleware(ErrorHandlerMiddleware)
        client = TestClient(app, raise_server_exceptions=True)

        with pytest.raises(RuntimeError, match="mid-stream failure"):
            client.get("/stream")


# =============================================================================
# Full stack (setup_middleware)
# =============================================================================


@pytest.mark.unit
class TestSetupMiddleware:
    """The full configured stack works end to end."""

    def test_full_stack_smoke(self):
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(request: Request) -> dict:
            return {"request_id": getattr(request.state, "request_id", None)}

        setup_middleware(app)
        client = TestClient(app)
        response = client.get("/test", headers={"X-Request-ID": "stack-1"})

        assert response.status_code == 200
        # RequestID ran (and reached the route through the whole stack)
        assert response.headers["X-Request-ID"] == "stack-1"
        assert response.json()["request_id"] == "stack-1"
        # SecurityHeaders ran
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_full_stack_error_path(self):
        app = FastAPI()

        @app.get("/error")
        async def error_endpoint() -> dict:
            raise ValueError("boom")

        setup_middleware(app)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        assert response.status_code == 500
        assert response.json()["error"] == "Internal server error"
        # Security headers apply to error responses too
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_websocket_scope_passthrough(self):
        """Non-http scopes traverse the stack untouched."""
        from fastapi import WebSocket

        app = FastAPI()

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket) -> None:
            await websocket.accept()
            await websocket.send_json({"ok": True})
            await websocket.close()

        setup_middleware(app)
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json() == {"ok": True}
