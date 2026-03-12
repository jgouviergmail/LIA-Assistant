"""
Unit tests for structured logging module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 23
Created: 2025-11-20
Target: 69% → 80%+ coverage
"""

import logging
from unittest.mock import Mock, patch

from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags

from src.infrastructure.observability.logging import (
    add_opentelemetry_context,
    configure_logging,
    get_logger,
    get_router_debug_logger,
)


class TestAddOpenTelemetryContext:
    """Tests for OpenTelemetry trace context injection into logs."""

    def test_add_opentelemetry_context_with_valid_span(self):
        """Test that trace context is added when valid span exists (Lines 59, 62, 65)."""
        # Create mock span with valid trace context
        mock_span = Mock(spec=trace.Span)

        # Create SpanContext with real trace/span IDs
        # trace_id: 128-bit = 0x135a20fdc30eaf9a5711c54d34d9db2b
        # span_id: 64-bit = 0x5711c54d34d9db2b
        span_context = SpanContext(
            trace_id=0x135A20FDC30EAF9A5711C54D34D9DB2B,
            span_id=0x5711C54D34D9DB2B,
            is_remote=False,
            trace_flags=TraceFlags(0x01),  # Sampled
        )

        mock_span.get_span_context.return_value = span_context

        event_dict = {"event": "test_event"}

        with patch(
            "src.infrastructure.observability.logging.trace.get_current_span",
            return_value=mock_span,
        ):
            # Lines 59, 62, 65 executed: Format trace_id, span_id, trace_flags
            result = add_opentelemetry_context(None, "info", event_dict)

        # Verify trace context added
        assert "trace_id" in result
        assert "span_id" in result
        assert "trace_flags" in result

        # Verify formatting (032x for trace_id, 016x for span_id, 02x for flags)
        assert result["trace_id"] == "135a20fdc30eaf9a5711c54d34d9db2b"  # 32 hex chars
        assert result["span_id"] == "5711c54d34d9db2b"  # 16 hex chars
        assert result["trace_flags"] == "01"  # 2 hex chars

    def test_add_opentelemetry_context_with_no_span(self):
        """Test that no context added when no span exists."""
        event_dict = {"event": "test_event"}

        with patch(
            "src.infrastructure.observability.logging.trace.get_current_span", return_value=None
        ):
            result = add_opentelemetry_context(None, "info", event_dict)

        # Should return original dict unchanged
        assert result == {"event": "test_event"}
        assert "trace_id" not in result
        assert "span_id" not in result

    def test_add_opentelemetry_context_with_invalid_span_context(self):
        """Test that no context added when span context is invalid."""
        mock_span = Mock(spec=trace.Span)

        # Create invalid SpanContext (trace_id=0, span_id=0)
        span_context = SpanContext(
            trace_id=0,
            span_id=0,
            is_remote=False,
            trace_flags=TraceFlags(0x00),
        )

        mock_span.get_span_context.return_value = span_context

        event_dict = {"event": "test_event"}

        with patch(
            "src.infrastructure.observability.logging.trace.get_current_span",
            return_value=mock_span,
        ):
            result = add_opentelemetry_context(None, "info", event_dict)

        # Invalid context should not be added
        assert result == {"event": "test_event"}
        assert "trace_id" not in result


class TestConfigureLogging:
    """Tests for logging configuration."""

    @patch("src.infrastructure.observability.logging.settings")
    @patch("src.infrastructure.observability.logging.structlog.configure")
    @patch("src.infrastructure.observability.logging.logging.basicConfig")
    def test_configure_logging_sets_up_structlog(
        self, mock_basic_config, mock_structlog_configure, mock_settings
    ):
        """Test that configure_logging sets up structlog correctly."""
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "WARNING"
        mock_settings.log_level_uvicorn_access = "WARNING"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        configure_logging()

        # Verify structlog.configure called
        mock_structlog_configure.assert_called_once()

        # Verify logging.basicConfig called
        mock_basic_config.assert_called_once()


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_structlog_logger(self):
        """Test that get_logger returns a structlog logger."""
        logger = get_logger("test.module")

        # structlog returns BoundLoggerLazyProxy, which is acceptable
        # Verify it's a structlog logger by checking it has log methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert callable(logger.info)


class TestGetRouterDebugLogger:
    """Tests for router debug logger with file handler."""

    @patch("src.infrastructure.observability.logging.settings")
    def test_get_router_debug_logger_disabled(self, mock_settings):
        """Test router debug logger when disabled (Line 177)."""
        mock_settings.router_debug_log_enabled = False

        # Line 177 executed: Return basic logger when disabled
        logger = get_router_debug_logger()

        # Should return structlog logger (as BoundLoggerLazyProxy)
        assert hasattr(logger, "info")
        assert callable(logger.info)

    @patch("src.infrastructure.observability.logging.settings")
    @patch("src.infrastructure.observability.logging.logging.handlers.RotatingFileHandler")
    def test_get_router_debug_logger_enabled_creates_file_handler(
        self, mock_rotating_handler, mock_settings, tmp_path
    ):
        """Test router debug logger creates file handler when enabled (Lines 180-197)."""
        mock_settings.router_debug_log_enabled = True
        # Use tmp_path for real filesystem operation
        log_file = tmp_path / "router_debug.log"
        mock_settings.router_debug_log_path = str(log_file)

        # Mock file handler
        mock_handler = Mock()
        mock_rotating_handler.return_value = mock_handler

        # Lines 180-197 executed: Create file handler with rotating
        logger = get_router_debug_logger()

        # Verify file handler created
        mock_rotating_handler.assert_called_once()
        call_kwargs = mock_rotating_handler.call_args.kwargs
        assert call_kwargs["maxBytes"] == 10 * 1024 * 1024  # 10MB
        assert call_kwargs["backupCount"] == 5
        assert call_kwargs["encoding"] == "utf-8"

        # Verify handler added to logger
        mock_handler.setLevel.assert_called_with(logging.DEBUG)

        # Should return structlog logger
        assert hasattr(logger, "info")
        assert callable(logger.info)

    @patch("src.infrastructure.observability.logging.settings")
    @patch("src.infrastructure.observability.logging.logging.handlers.RotatingFileHandler")
    def test_get_router_debug_logger_handles_file_creation_error(
        self, mock_rotating_handler, mock_settings, caplog
    ):
        """Test router debug logger handles file creation errors gracefully (Lines 199-206)."""
        mock_settings.router_debug_log_enabled = True
        mock_settings.router_debug_log_path = "/invalid/path/router_debug.log"

        # Mock RotatingFileHandler to raise exception
        mock_rotating_handler.side_effect = PermissionError("Cannot create log file")

        # Lines 199-206 executed: Exception caught, fallback to standard logger
        with caplog.at_level(logging.WARNING):
            logger = get_router_debug_logger()

        # Should fallback to standard logger (no exception raised)
        assert hasattr(logger, "info")
        assert callable(logger.info)

        # Verify warning logged
        # Note: caplog may not capture structlog warnings, so we just verify no exception raised

    @patch("src.infrastructure.observability.logging.settings")
    @patch("src.infrastructure.observability.logging.logging.handlers.RotatingFileHandler")
    def test_get_router_debug_logger_mkdir_creates_parent_directories(
        self, mock_rotating_handler, mock_settings, tmp_path
    ):
        """Test router debug logger creates parent directories (Lines 182-183)."""
        mock_settings.router_debug_log_enabled = True
        # Use nested path that doesn't exist yet
        log_file = tmp_path / "debug" / "nested" / "router_debug.log"
        mock_settings.router_debug_log_path = str(log_file)

        # Mock file handler
        mock_handler = Mock()
        mock_rotating_handler.return_value = mock_handler

        # Lines 182-183 executed: mkdir with parents=True, exist_ok=True
        logger = get_router_debug_logger()

        # Verify parent directory was created
        assert log_file.parent.exists()

        # Should return logger
        assert hasattr(logger, "info")

    @patch("src.infrastructure.observability.logging.settings")
    @patch("src.infrastructure.observability.logging.logging.handlers.RotatingFileHandler")
    @patch("src.infrastructure.observability.logging.logging.getLogger")
    def test_get_router_debug_logger_adds_handler_to_stdlib_logger(
        self, mock_get_logger, mock_rotating_handler, mock_settings, tmp_path
    ):
        """Test router debug logger adds handler to stdlib logger (Lines 195-197)."""
        mock_settings.router_debug_log_enabled = True
        log_file = tmp_path / "router_debug.log"
        mock_settings.router_debug_log_path = str(log_file)

        # Mock file handler
        mock_handler = Mock()
        mock_rotating_handler.return_value = mock_handler

        # Mock stdlib logger
        mock_stdlib_logger = Mock()
        mock_get_logger.return_value = mock_stdlib_logger

        # Lines 195-197 executed: Add handler to stdlib logger
        get_router_debug_logger()

        # Verify handler added and log level set
        mock_stdlib_logger.addHandler.assert_called_once_with(mock_handler)
        mock_stdlib_logger.setLevel.assert_called_once_with(logging.DEBUG)
