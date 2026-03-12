"""
Structured logging configuration using structlog.
Provides JSON logging for production and pretty console logging for development.

Security Features:
- PII (Personally Identifiable Information) detection and redaction
- Email pseudonymization (SHA-256 hash)
- Phone number masking
- Sensitive field filtering (passwords, tokens, secrets)
- GDPR compliance
"""

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace

from src.core.config import settings
from src.infrastructure.observability.pii_filter import add_pii_filter


def add_opentelemetry_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Inject OpenTelemetry trace context into structured logs.

    Automatically adds trace_id, span_id, and trace_flags from the current
    OpenTelemetry span context to enable logs-traces correlation in Grafana.

    Args:
        logger: The logger instance
        method_name: The name of the log method called
        event_dict: The event dictionary to be logged

    Returns:
        The event dictionary enriched with OpenTelemetry context

    Example log output:
        {
            "event": "router_decision",
            "trace_id": "135a20fdc30eaf9a5711c54d34d9db2b",
            "span_id": "5711c54d34d9db2b",
            "trace_flags": "01",
            ...
        }
    """
    # Get current OpenTelemetry span
    span = trace.get_current_span()

    if span:
        span_context = span.get_span_context()

        # Only inject if we have a valid trace context
        if span_context.is_valid:
            # Format trace_id as 32-character hex string (128-bit)
            event_dict["trace_id"] = format(span_context.trace_id, "032x")

            # Format span_id as 16-character hex string (64-bit)
            event_dict["span_id"] = format(span_context.span_id, "016x")

            # Add trace flags (sampled or not)
            event_dict["trace_flags"] = format(span_context.trace_flags, "02x")

    return event_dict


def configure_logging() -> None:
    """
    Configure structlog with appropriate processors for environment.

    All environments: JSON output for log aggregation (Loki, Promtail)
    Note: Changed from pretty console to JSON in dev for Promtail parsing
    """
    # Determine log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared processors for all environments
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_opentelemetry_context,  # Inject trace_id and span_id for correlation
        add_pii_filter,  # CRITICAL: Filter PII before rendering (GDPR compliance)
    ]

    # Always use JSON output for Promtail/Loki parsing
    # (even in development since Promtail is configured)
    processors = shared_processors + [
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]

    # Configure structlog
    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Set log levels for third-party libraries (configurable via .env)
    logging.getLogger("uvicorn").setLevel(getattr(logging, str(settings.log_level_uvicorn).upper()))
    logging.getLogger("uvicorn.access").setLevel(
        getattr(logging, str(settings.log_level_uvicorn_access).upper())
    )
    logging.getLogger("sqlalchemy.engine").setLevel(
        getattr(logging, str(settings.log_level_sqlalchemy).upper())
    )
    logging.getLogger("httpx").setLevel(getattr(logging, str(settings.log_level_httpx).upper()))
    # httpcore is the low-level HTTP transport used by httpx/OpenAI SDK
    # Must be silenced to avoid raw HTTP traces (receive_response_headers, etc.)
    logging.getLogger("httpcore").setLevel(getattr(logging, str(settings.log_level_httpx).upper()))
    # OpenAI SDK uses its own logger for request/response logging
    logging.getLogger("openai").setLevel(getattr(logging, str(settings.log_level_httpx).upper()))
    logging.getLogger("openai._base_client").setLevel(
        getattr(logging, str(settings.log_level_httpx).upper())
    )

    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        environment=settings.environment,
        log_level=settings.log_level,
        log_level_httpx=settings.log_level_httpx,
        log_level_sqlalchemy=settings.log_level_sqlalchemy,
        production_mode=settings.is_production,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def get_router_debug_logger() -> structlog.stdlib.BoundLogger:
    """
    Get a dedicated logger for router debugging.
    Logs router reasoning and decisions to a separate file for audit purposes.

    Only active if ROUTER_DEBUG_LOG_ENABLED=true in configuration.

    Returns:
        Configured structlog logger for router debugging.

    Example:
        >>> router_debug_logger = get_router_debug_logger()
        >>> router_debug_logger.info("router_reasoning",
        ...     run_id=run_id,
        ...     intention=output.intention,
        ...     confidence=output.confidence,
        ...     reasoning=output.reasoning
        ... )
    """
    import logging.handlers
    from pathlib import Path

    logger_name = "router_debug"

    # Return basic logger if debug logging disabled
    if not settings.router_debug_log_enabled:
        return structlog.get_logger(logger_name)  # type: ignore[no-any-return]

    # Create dedicated file handler for router debug logs
    try:
        # Ensure log directory exists
        log_path = Path(settings.router_debug_log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create rotating file handler (max 10MB, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        # Add handler to stdlib logger
        stdlib_logger = logging.getLogger(logger_name)
        stdlib_logger.addHandler(file_handler)
        stdlib_logger.setLevel(logging.DEBUG)

    except Exception as e:
        # Fallback to standard logger if file creation fails
        base_logger = structlog.get_logger(__name__)
        base_logger.warning(
            "router_debug_log_setup_failed",
            error=str(e),
            fallback_to_standard_logging=True,
        )

    return structlog.get_logger(logger_name)  # type: ignore[no-any-return]
