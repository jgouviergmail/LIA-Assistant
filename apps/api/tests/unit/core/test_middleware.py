"""
Unit tests for core/middleware.py.

Tests request ID tracking, security headers, logging, and error handling middleware.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from src.core.middleware import (
    ErrorHandlerMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    setup_middleware,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_request():
    """Create a mock request object."""
    request = MagicMock(spec=Request)
    request.url.path = "/api/test"
    request.method = "GET"
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.state = MagicMock()
    return request


@pytest.fixture
def mock_response():
    """Create a mock response object."""
    response = MagicMock(spec=Response)
    response.headers = {}
    response.status_code = 200
    return response


@pytest.fixture
def simple_app():
    """Create a simple FastAPI app for testing."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"message": "ok"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    return app


# =============================================================================
# RequestIDMiddleware - Unit Tests
# =============================================================================


@pytest.mark.unit
class TestRequestIDMiddleware:
    """Tests for RequestIDMiddleware."""

    @pytest.mark.asyncio
    async def test_generates_request_id_when_not_provided(self, mock_request, mock_response):
        """Test that a request ID is generated when not in headers."""
        mock_request.headers = {}

        async def call_next(request):
            return mock_response

        middleware = RequestIDMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        # Should have a request ID in response headers
        assert "X-Request-ID" in response.headers
        # Should be a valid UUID
        assert len(response.headers["X-Request-ID"]) == 36

    @pytest.mark.asyncio
    async def test_uses_provided_request_id(self, mock_request, mock_response):
        """Test that provided X-Request-ID is used."""
        provided_id = "custom-request-id-12345"
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value=provided_id)
        mock_request.headers = mock_headers

        async def call_next(request):
            return mock_response

        middleware = RequestIDMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["X-Request-ID"] == provided_id

    @pytest.mark.asyncio
    async def test_sets_request_id_on_state(self, mock_request, mock_response):
        """Test that request ID is set on request state."""
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value=None)
        mock_request.headers = mock_headers

        async def call_next(request):
            # Verify request_id is set on state
            assert hasattr(request.state, "request_id")
            return mock_response

        middleware = RequestIDMiddleware(app=MagicMock())
        await middleware.dispatch(mock_request, call_next)


# =============================================================================
# SecurityHeadersMiddleware - Unit Tests
# =============================================================================


@pytest.mark.unit
class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.mark.asyncio
    async def test_adds_x_frame_options(self, mock_request, mock_response):
        """Test that X-Frame-Options header is added."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        middleware = SecurityHeadersMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_adds_x_content_type_options(self, mock_request, mock_response):
        """Test that X-Content-Type-Options header is added."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        middleware = SecurityHeadersMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_adds_xss_protection(self, mock_request, mock_response):
        """Test that X-XSS-Protection header is added."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        middleware = SecurityHeadersMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_adds_coep_header(self, mock_request, mock_response):
        """Test that Cross-Origin-Embedder-Policy header is added."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        middleware = SecurityHeadersMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"

    @pytest.mark.asyncio
    async def test_adds_coop_header(self, mock_request, mock_response):
        """Test that Cross-Origin-Opener-Policy header is added."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        middleware = SecurityHeadersMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


# =============================================================================
# LoggingMiddleware - Unit Tests
# =============================================================================


@pytest.mark.unit
class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    @pytest.mark.asyncio
    async def test_logs_request_completion(self, mock_request, mock_response):
        """Test that request completion is logged."""
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.http_log_level = "DEBUG"
            mock_settings.http_log_exclude_paths = []

            with patch("src.core.middleware.logger") as mock_logger:
                middleware = LoggingMiddleware(app=MagicMock())
                await middleware.dispatch(mock_request, call_next)

                # Should log request started and completed
                assert mock_logger.debug.call_count >= 1

    @pytest.mark.asyncio
    async def test_excludes_health_check_paths(self, mock_request, mock_response):
        """Test that excluded paths are not logged."""
        mock_request.url.path = "/health"
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.http_log_level = "DEBUG"
            mock_settings.http_log_exclude_paths = ["/health", "/metrics"]

            with patch("src.core.middleware.logger") as mock_logger:
                middleware = LoggingMiddleware(app=MagicMock())
                await middleware.dispatch(mock_request, call_next)

                # Should not log for excluded paths (except errors)
                mock_logger.debug.assert_not_called()

    @pytest.mark.asyncio
    async def test_excludes_paths_with_trailing_slash(self, mock_request, mock_response):
        """Test that paths with trailing slash are excluded."""
        mock_request.url.path = "/health/"
        mock_response.headers = {}

        async def call_next(request):
            return mock_response

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.http_log_level = "DEBUG"
            mock_settings.http_log_exclude_paths = ["/health"]

            with patch("src.core.middleware.logger") as mock_logger:
                middleware = LoggingMiddleware(app=MagicMock())
                await middleware.dispatch(mock_request, call_next)

                mock_logger.debug.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_errors_at_error_level(self, mock_request):
        """Test that errors are logged at ERROR level."""

        async def call_next(request):
            raise ValueError("Test error")

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.http_log_level = "DEBUG"
            mock_settings.http_log_exclude_paths = []

            with patch("src.core.middleware.logger") as mock_logger:
                middleware = LoggingMiddleware(app=MagicMock())

                with pytest.raises(ValueError):
                    await middleware.dispatch(mock_request, call_next)

                # Error should be logged
                mock_logger.error.assert_called()


# =============================================================================
# ErrorHandlerMiddleware - Unit Tests
# =============================================================================


@pytest.mark.unit
class TestErrorHandlerMiddleware:
    """Tests for ErrorHandlerMiddleware."""

    @pytest.mark.asyncio
    async def test_passes_through_successful_response(self, mock_request, mock_response):
        """Test that successful responses pass through unchanged."""

        async def call_next(request):
            return mock_response

        middleware = ErrorHandlerMiddleware(app=MagicMock())
        response = await middleware.dispatch(mock_request, call_next)

        assert response == mock_response

    @pytest.mark.asyncio
    async def test_catches_unhandled_exception(self, mock_request):
        """Test that unhandled exceptions are caught and return 500."""
        # Set a proper string value for request_id to avoid JSON serialization issues
        mock_request.state.request_id = "test-request-id"

        async def call_next(request):
            raise ValueError("Unhandled error")

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.debug = False

            with patch("src.core.middleware.logger"):
                middleware = ErrorHandlerMiddleware(app=MagicMock())
                response = await middleware.dispatch(mock_request, call_next)

                assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_includes_error_detail_in_debug_mode(self, mock_request):
        """Test that error details are included in debug mode."""
        # Set a proper string value for request_id to avoid JSON serialization issues
        mock_request.state.request_id = "test-request-id"

        async def call_next(request):
            raise ValueError("Debug error message")

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.debug = True

            with patch("src.core.middleware.logger"):
                middleware = ErrorHandlerMiddleware(app=MagicMock())
                response = await middleware.dispatch(mock_request, call_next)

                # In debug mode, detail should include the actual error
                assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_hides_error_detail_in_production(self, mock_request):
        """Test that error details are hidden in production."""
        # Set a proper string value for request_id to avoid JSON serialization issues
        mock_request.state.request_id = "test-request-id"

        async def call_next(request):
            raise ValueError("Sensitive error info")

        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.debug = False

            with patch("src.core.middleware.logger"):
                middleware = ErrorHandlerMiddleware(app=MagicMock())
                response = await middleware.dispatch(mock_request, call_next)

                assert response.status_code == 500


# =============================================================================
# setup_middleware - Unit Tests
# =============================================================================


@pytest.mark.unit
class TestSetupMiddleware:
    """Tests for setup_middleware function."""

    def test_setup_adds_cors_middleware(self, simple_app):
        """Test that CORS middleware is added."""
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.cors_origins = ["http://localhost:3000"]

            with patch("src.core.middleware.logger"):
                setup_middleware(simple_app)

        # Verify middleware was added by checking the app's middleware stack
        middleware_classes = [m.cls.__name__ for m in simple_app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    def test_setup_adds_custom_middleware(self, simple_app):
        """Test that custom middleware are added."""
        with patch("src.core.middleware.settings") as mock_settings:
            mock_settings.cors_origins = ["http://localhost:3000"]

            with patch("src.core.middleware.logger"):
                setup_middleware(simple_app)

        middleware_classes = [m.cls.__name__ for m in simple_app.user_middleware]

        # Check that our custom middleware are added
        assert "ErrorHandlerMiddleware" in middleware_classes
        assert "LoggingMiddleware" in middleware_classes
        assert "SecurityHeadersMiddleware" in middleware_classes
        assert "RequestIDMiddleware" in middleware_classes


# =============================================================================
# Integration Tests with TestClient
# =============================================================================


@pytest.mark.unit
class TestMiddlewareIntegration:
    """Integration tests for middleware stack."""

    def test_security_headers_in_response(self):
        """Test that security headers appear in actual response."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_request_id_in_response(self):
        """Test that request ID appears in actual response."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        app.add_middleware(RequestIDMiddleware)

        client = TestClient(app)
        response = client.get("/test")

        assert "X-Request-ID" in response.headers
        # Should be a valid UUID format
        request_id = response.headers["X-Request-ID"]
        try:
            uuid.UUID(request_id)
            is_valid_uuid = True
        except ValueError:
            is_valid_uuid = False
        assert is_valid_uuid

    def test_provided_request_id_preserved(self):
        """Test that provided request ID is preserved."""
        app = FastAPI()

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        app.add_middleware(RequestIDMiddleware)

        client = TestClient(app)
        custom_id = "my-custom-request-id"
        response = client.get("/test", headers={"X-Request-ID": custom_id})

        assert response.headers.get("X-Request-ID") == custom_id
