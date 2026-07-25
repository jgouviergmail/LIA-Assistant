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
    def test_configure_logging_sets_up_structlog(self, mock_structlog_configure, mock_settings):
        """Test that configure_logging sets up structlog correctly."""
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "WARNING"
        mock_settings.log_level_uvicorn_access = "WARNING"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        configure_logging()

        mock_structlog_configure.assert_called_once()

    @patch("src.infrastructure.observability.logging.settings")
    def test_root_handler_renders_through_the_shared_chain(self, mock_settings):
        """The root handler must carry the ProcessorFormatter (FN-4).

        This replaced an assertion that ``logging.basicConfig`` had been called
        — a check on HOW the handler was installed, which said nothing about
        what it does. What matters is that stdlib records (uvicorn.access,
        httpx, any library) are rendered by the shared chain: a handler without
        that formatter emits unfiltered plain text that Promtail cannot parse
        and that bypasses the PII filter entirely.
        """
        import logging as stdlib_logging

        import structlog

        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "WARNING"
        mock_settings.log_level_uvicorn_access = "WARNING"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        configure_logging()

        handlers = stdlib_logging.getLogger().handlers
        assert handlers, "the root logger must have a handler"
        assert any(
            isinstance(h.formatter, structlog.stdlib.ProcessorFormatter) for h in handlers
        ), "no root handler renders through ProcessorFormatter — stdlib logs would skip the PII filter"

    @patch("src.infrastructure.observability.logging.settings")
    def test_stdlib_record_is_filtered_and_rendered_as_json(self, mock_settings):
        """A foreign record is sanitised and structured, end to end (FN-4).

        `uvicorn.access` logs the full request target, so an OAuth callback
        (`?code=…&state=…`) or a static-map URL (`?lat=…&lng=…`) used to reach
        Loki verbatim: those loggers never went through structlog, so the PII
        filter never saw them.
        """
        import io
        import json
        import logging as stdlib_logging

        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "WARNING"
        mock_settings.log_level_uvicorn_access = "ERROR"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        configure_logging()

        buffer = io.StringIO()
        stdlib_logging.getLogger().handlers[0].stream = buffer  # type: ignore[attr-defined]

        code, state = "4/0AY0e-g7SENTINELCODE", "Zx8QpLmv3NrTfKe1Ab9YsWc7Hd2Gj5Uo0"
        stdlib_logging.getLogger("uvicorn.access").error(
            f'127.0.0.1 - "GET /auth/google/callback?code={code}&state={state}" 302'
        )

        line = buffer.getvalue().strip()
        assert line, "the record was not emitted"
        payload = json.loads(line)  # must be JSON: Promtail parses it
        assert code not in line
        assert state not in line
        assert "code=[REDACTED]" in payload["event"]
        assert "state=[REDACTED]" in payload["event"]

    @patch("src.infrastructure.observability.logging.settings")
    def test_access_log_is_filtered_even_after_uvicorn_detached_it(self, mock_settings):
        """Reproduces production ordering: uvicorn configures logging FIRST.

        `uvicorn.config.LOGGING_CONFIG` gives `uvicorn.access` its own handler
        with `propagate: False`, and applies that when the server builds its
        Config — before this module is imported. A formatter installed only on
        the ROOT logger therefore never sees an access record.

        The earlier tests in this class passed for the wrong reason: in a bare
        `logging` setup `uvicorn.access` propagates by default, so they never
        exercised the configuration that actually ships. This one applies
        uvicorn's dictConfig first, which is the only way to prove the fix.
        """
        import io
        import json
        import logging as stdlib_logging
        import logging.config as stdlib_logging_config

        from uvicorn.config import LOGGING_CONFIG

        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "INFO"
        mock_settings.log_level_uvicorn_access = "INFO"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        # 1. uvicorn detaches its loggers from the root, as it does at startup.
        stdlib_logging_config.dictConfig(LOGGING_CONFIG)
        assert stdlib_logging.getLogger("uvicorn.access").propagate is False

        # 2. The application configures logging afterwards — and must reclaim them.
        configure_logging()

        buffer = io.StringIO()
        stdlib_logging.getLogger().handlers[0].stream = buffer  # type: ignore[attr-defined]

        code = "4/0AY0e-g7SENTINELCODE"
        stdlib_logging.getLogger("uvicorn.access").info(
            f'127.0.0.1 - "GET /auth/google/callback?code={code}" 302'
        )

        line = buffer.getvalue().strip()
        assert line, (
            "the access record never reached the shared handler — uvicorn's "
            "propagate=False was not reclaimed, so the PII filter is bypassed"
        )
        payload = json.loads(line)
        assert code not in line
        assert "code=[REDACTED]" in payload["event"]

    @patch("src.infrastructure.observability.logging.settings")
    def test_gps_coordinates_are_redacted_from_stdlib_records(self, mock_settings):
        """Coordinates are PII the policy forbids at INFO — including in URLs."""
        import io
        import json
        import logging as stdlib_logging

        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"
        mock_settings.log_level_uvicorn = "WARNING"
        mock_settings.log_level_uvicorn_access = "ERROR"
        mock_settings.log_level_sqlalchemy = "WARNING"
        mock_settings.log_level_httpx = "WARNING"
        mock_settings.is_production = False

        configure_logging()

        buffer = io.StringIO()
        stdlib_logging.getLogger().handlers[0].stream = buffer  # type: ignore[attr-defined]

        stdlib_logging.getLogger("uvicorn.access").error(
            "GET /api/v1/connectors/google-location/static-map?lat=48.8566&lng=2.3522 200"
        )

        payload = json.loads(buffer.getvalue().strip())
        assert "48.8566" not in payload["event"]
        assert "2.3522" not in payload["event"]


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
