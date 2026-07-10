"""Base API exception with automatic logging and Prometheus metrics.

Internal module (``_`` prefix): holds ``BaseAPIException`` so that both the
central taxonomy (``src.core.exceptions``) and the domain-specific families
(``src.core.exceptions_domains``) can subclass it without a circular import.
Consumers keep importing everything from ``src.core.exceptions`` (façade).

ADR Reference: ADR-002 (Unified Error Handling), ADR-124 (rule #18 phase 2).
"""

from typing import Any

from fastapi import HTTPException

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class BaseAPIException(HTTPException):
    """
    Base exception class for all API exceptions.

    Provides automatic structured logging, i18n support, and Prometheus metrics.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        log_level: str = "warning",
        log_event: str | None = None,
        headers: dict[str, str] | None = None,
        **log_context: Any,
    ) -> None:
        """
        Initialize API exception with automatic logging and metrics.

        Args:
            status_code: HTTP status code
            detail: Error message (user-facing)
            log_level: Logging level (debug, info, warning, error, critical)
            log_event: Structured log event name (defaults to detail)
            headers: Optional HTTP response headers (e.g. Retry-After,
                X-Requires-Reconnect) forwarded to the FastAPI response
            **log_context: Additional context for structured logging
        """
        super().__init__(status_code=status_code, detail=detail, headers=headers)

        # Automatic structured logging
        log_method = getattr(logger, log_level, logger.warning)
        log_method(log_event or detail.lower().replace(" ", "_"), **log_context)

        # METRICS: Track HTTP errors by status code and exception type
        from src.infrastructure.observability.metrics_errors import (
            http_client_errors_total,
            http_errors_total,
            http_server_errors_total,
        )

        exception_type = self.__class__.__name__
        endpoint = log_context.get("endpoint", "unknown")

        # Track general HTTP errors
        http_errors_total.labels(
            status_code=str(status_code),
            exception_type=exception_type,
            endpoint=endpoint,
        ).inc()

        # Track specific client/server error categories
        if 400 <= status_code < 500:
            # Client errors (4xx)
            error_type = self._classify_client_error(status_code, log_event)
            http_client_errors_total.labels(error_type=error_type).inc()

        elif 500 <= status_code < 600:
            # Server errors (5xx)
            error_type = self._classify_server_error(status_code, log_event)
            http_server_errors_total.labels(error_type=error_type).inc()

    @staticmethod
    def _classify_client_error(status_code: int, log_event: str | None) -> str:
        """
        Classify 4xx client errors into standard categories for metrics.

        Error taxonomy:
        - authentication_failed: 401 Unauthorized
        - authorization_failed: 403 Forbidden
        - resource_not_found: 404 Not Found
        - resource_conflict: 409 Conflict
        - validation_failed: 400 Bad Request, 422 Unprocessable Entity
        - rate_limit_exceeded: 429 Too Many Requests
        """
        if status_code == 401:
            return "authentication_failed"
        elif status_code == 403:
            return "authorization_failed"
        elif status_code == 404:
            return "resource_not_found"
        elif status_code == 409:
            return "resource_conflict"
        elif status_code == 429:
            return "rate_limit_exceeded"
        elif status_code in (400, 422):
            return "validation_failed"
        else:
            return "client_error_other"

    @staticmethod
    def _classify_server_error(status_code: int, log_event: str | None) -> str:
        """
        Classify 5xx server errors into standard categories for metrics.

        Error taxonomy:
        - external_service_error: 503 Service Unavailable (OAuth, API calls)
        - database_error: 500 with database context
        - llm_service_error: 500 with LLM context
        - timeout_error: 504 Gateway Timeout
        - internal_server_error: 500 other
        """
        if status_code == 503:
            # Check log_event for service type
            if log_event and "service_error" in log_event:
                return "external_service_error"
            return "service_unavailable"
        elif status_code == 504:
            return "timeout_error"
        elif status_code == 500:
            # Infer from log_event
            if log_event:
                if "database" in log_event or "db" in log_event:
                    return "database_error"
                elif "llm" in log_event or "openai" in log_event or "anthropic" in log_event:
                    return "llm_service_error"
            return "internal_server_error"
        else:
            return "server_error_other"
