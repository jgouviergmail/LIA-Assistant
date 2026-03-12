"""
Tests for HTTP request logging middleware.

Validates that LoggingMiddleware correctly:
- Uses configurable log levels (DEBUG/INFO)
- Excludes specified paths from logging
- Respects HTTP_LOG_LEVEL and HTTP_LOG_EXCLUDE_PATHS settings

Coverage:
- Path exclusion (e.g., /metrics, /health)
- Log level configuration (DEBUG vs INFO)
- Settings integration
"""

import os
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from src.core.config import Settings
from src.core.constants import HTTP_LOG_EXCLUDE_PATHS_DEFAULT, HTTP_LOG_LEVEL_DEFAULT
from src.core.middleware import LoggingMiddleware


def create_test_app():
    """Create test app with routes."""
    app = Starlette()

    @app.route("/test")
    async def test_endpoint(_request):
        return JSONResponse({"status": "ok"})

    @app.route("/metrics")
    async def metrics_endpoint(_request):
        return JSONResponse({"metrics": "data"})

    @app.route("/health")
    async def health_endpoint(_request):
        return JSONResponse({"health": "ok"})

    return app


# ============================================================================
# Path Exclusion Tests
# ============================================================================


def test_excluded_path_not_logged():
    """Test that excluded paths (/metrics, /health) are not logged."""
    app = create_test_app()
    settings = Settings()
    settings.http_log_level = "DEBUG"
    settings.http_log_exclude_paths = ["/metrics", "/health"]

    with patch("src.core.middleware.settings", settings):
        app.add_middleware(LoggingMiddleware)

    client = TestClient(app)

    with patch("src.core.middleware.logger") as mock_logger:
        response = client.get("/metrics")
        assert response.status_code == 200

        # Verify /metrics was NOT logged (no debug calls with /metrics path)
        all_log_calls = str(mock_logger.debug.call_args_list)
        assert "/metrics" not in all_log_calls, "Excluded path should not be logged"


def test_included_path_is_logged():
    """Test that non-excluded paths are logged."""
    app = create_test_app()
    settings = Settings()
    settings.http_log_level = "DEBUG"
    settings.http_log_exclude_paths = ["/metrics"]

    with patch("src.core.middleware.settings", settings):
        app.add_middleware(LoggingMiddleware)

    client = TestClient(app)

    with patch("src.core.middleware.logger") as mock_logger:
        response = client.get("/test")
        assert response.status_code == 200

        # Verify logger.debug was called with /test path
        assert mock_logger.debug.called
        all_calls = str(mock_logger.debug.call_args_list)
        assert "request_started" in all_calls and "/test" in all_calls


# ============================================================================
# Log Level Configuration Tests
# ============================================================================


def test_debug_log_level_uses_debug_method():
    """Test that DEBUG log level calls logger.debug()."""
    app = create_test_app()
    settings = Settings()
    settings.http_log_level = "DEBUG"
    settings.http_log_exclude_paths = []

    with patch("src.core.middleware.settings", settings):
        app.add_middleware(LoggingMiddleware)

    client = TestClient(app)

    with patch("src.core.middleware.logger") as mock_logger:
        response = client.get("/test")
        assert response.status_code == 200

        # Verify debug() was called (not info())
        assert mock_logger.debug.called
        assert mock_logger.info.call_count == 0


def test_info_log_level_uses_info_method():
    """Test that INFO log level calls logger.info()."""
    app = create_test_app()

    # Create settings with INFO level before adding middleware
    settings = Settings()
    settings.http_log_level = "INFO"
    settings.http_log_exclude_paths = []

    with patch("src.core.middleware.settings", settings):
        with patch("src.core.middleware.logger") as mock_logger:
            app.add_middleware(LoggingMiddleware)
            client = TestClient(app)

            response = client.get("/test")
            assert response.status_code == 200

            # Verify info() was called (not debug())
            assert mock_logger.info.called
            assert mock_logger.debug.call_count == 0


# ============================================================================
# Settings Integration Tests
# ============================================================================


def test_settings_http_log_exclude_paths_from_env():
    """Test that HTTP_LOG_EXCLUDE_PATHS is correctly parsed from environment."""
    # Test comma-separated string parsing (must use JSON array format for Pydantic)
    env_vars = {
        "HTTP_LOG_EXCLUDE_PATHS": '"/api/v1/health,/metrics,/status"',
        # Alternatively, test with JSON array format
        # "HTTP_LOG_EXCLUDE_PATHS": '["/api/v1/health", "/metrics", "/status"]'
    }
    with patch.dict(os.environ, env_vars, clear=False):
        settings = Settings()
        # The validator converts comma-separated string to list
        assert settings.http_log_exclude_paths == ["/api/v1/health", "/metrics", "/status"]


def test_settings_http_log_level_from_env():
    """Test that HTTP_LOG_LEVEL is correctly loaded from environment."""
    with patch.dict(os.environ, {"HTTP_LOG_LEVEL": "INFO"}, clear=False):
        settings = Settings()
        assert settings.http_log_level == "INFO"

    with patch.dict(os.environ, {"HTTP_LOG_LEVEL": "DEBUG"}, clear=False):
        settings = Settings()
        assert settings.http_log_level == "DEBUG"


def test_settings_http_log_exclude_paths_default():
    """Test that HTTP_LOG_EXCLUDE_PATHS has correct default value."""
    settings = Settings()
    assert settings.http_log_exclude_paths == HTTP_LOG_EXCLUDE_PATHS_DEFAULT


def test_settings_http_log_level_default():
    """Test that HTTP_LOG_LEVEL has correct default value."""
    settings = Settings()
    assert settings.http_log_level == HTTP_LOG_LEVEL_DEFAULT


# ============================================================================
# Integration Test
# ============================================================================


def test_full_request_response_cycle_with_exclusion():
    """Integration test: Full request/response cycle with path exclusion."""
    app = create_test_app()

    settings = Settings()
    settings.http_log_level = "DEBUG"
    settings.http_log_exclude_paths = ["/health"]

    with patch("src.core.middleware.settings", settings):
        app.add_middleware(LoggingMiddleware)

    client = TestClient(app)

    with patch("src.core.middleware.logger") as mock_logger:
        # Request to included path - should be logged
        response1 = client.get("/test")
        assert response1.status_code == 200

        # Request to excluded path - should NOT be logged
        response2 = client.get("/health")
        assert response2.status_code == 200

        # Verify /test was logged but /health was not
        all_calls = str(mock_logger.debug.call_args_list)
        assert "/test" in all_calls, "/test should be logged"
        assert "/health" not in all_calls, "/health should not be logged"


def test_constants_used_correctly():
    """Test that middleware uses constants from src.core.constants."""
    # Verify constants exist and have expected values
    assert HTTP_LOG_LEVEL_DEFAULT == "DEBUG"
    assert "/metrics" in HTTP_LOG_EXCLUDE_PATHS_DEFAULT
    assert "/health" in HTTP_LOG_EXCLUDE_PATHS_DEFAULT

    # Verify Settings uses these constants
    settings = Settings()
    assert settings.http_log_level == HTTP_LOG_LEVEL_DEFAULT
    assert settings.http_log_exclude_paths == HTTP_LOG_EXCLUDE_PATHS_DEFAULT
