"""
Unified exception handling for LIA API.

This module centralizes all HTTP exceptions and error handling to follow DRY principle.
It provides type-safe exception classes and helper functions for common error scenarios.

Design principles:
    - Single source of truth for error messages and status codes
    - Automatic logging integration with structured logging
    - Internationalization support (i18n) for error messages
    - Security-aware error handling (OWASP enumeration prevention)

Usage:
    from src.core.exceptions import raise_user_not_found, raise_invalid_credentials

    # In service methods
    if not user:
        raise_user_not_found(user_id)

    if not verify_password(password, user.hashed_password):
        raise_invalid_credentials()

ADR Reference: ADR-002 (Unified Error Handling)
"""

from typing import TYPE_CHECKING, Any, NoReturn
from uuid import UUID

from fastapi import HTTPException, status

from src.core.field_names import FIELD_USER_ID
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.i18n_api_messages import SupportedLanguage

logger = get_logger(__name__)


# ============================================================================
# Custom Exception Classes
# ============================================================================


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
        **log_context: Any,
    ) -> None:
        """
        Initialize API exception with automatic logging and metrics.

        Args:
            status_code: HTTP status code
            detail: Error message (user-facing)
            log_level: Logging level (debug, info, warning, error, critical)
            log_event: Structured log event name (defaults to detail)
            **log_context: Additional context for structured logging
        """
        super().__init__(status_code=status_code, detail=detail)

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


class AuthenticationError(BaseAPIException):
    """Authentication failed - invalid credentials or token."""

    def __init__(self, detail: str = "Invalid credentials", **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            log_level="warning",
            log_event="authentication_failed",
            **log_context,
        )


class AuthorizationError(BaseAPIException):
    """Authorization failed - insufficient permissions."""

    def __init__(
        self,
        detail: str = "Not authorized to access this resource",
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            log_level="warning",
            log_event="authorization_failed",
            **log_context,
        )


class ResourceNotFoundError(BaseAPIException):
    """Resource not found in database."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str | UUID | None = None,
        detail: str | None = None,
        **log_context: Any,
    ) -> None:
        # Use custom detail if provided, otherwise generate default
        final_detail = detail or f"{resource_type.capitalize()} not found"

        if resource_id:
            log_context["resource_id"] = str(resource_id)

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=final_detail,
            log_level="warning",
            log_event=f"{resource_type}_not_found",
            resource_type=resource_type,
            **log_context,
        )


class ResourceConflictError(BaseAPIException):
    """Resource conflict - duplicate or constraint violation."""

    def __init__(
        self,
        resource_type: str,
        detail: str | None = None,
        **log_context: Any,
    ) -> None:
        detail = detail or f"{resource_type.capitalize()} already exists"

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            log_level="warning",
            log_event=f"{resource_type}_conflict",
            resource_type=resource_type,
            **log_context,
        )


class ValidationError(BaseAPIException):
    """Validation failed - invalid input data."""

    def __init__(self, detail: str, **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            log_level="warning",
            log_event="validation_failed",
            **log_context,
        )


class MaxRetriesExceededError(Exception):
    """
    Raised when maximum retry attempts have been exhausted.

    This exception is used by the retry decorator and client methods
    to signal that all retry attempts have failed.

    Attributes:
        operation: Name of the operation that failed
        max_retries: Number of retry attempts made
        last_error: The last exception encountered
    """

    def __init__(
        self,
        operation: str,
        max_retries: int,
        last_error: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.max_retries = max_retries
        self.last_error = last_error
        message = f"Max retries ({max_retries}) exceeded for {operation}"
        if last_error:
            message = f"{message}: {last_error!s}"
        super().__init__(message)


class ExternalServiceError(BaseAPIException):
    """External service error - OAuth, API calls, etc."""

    def __init__(
        self,
        service_name: str,
        detail: str | None = None,
        **log_context: Any,
    ) -> None:
        detail = detail or f"{service_name} service unavailable"

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            log_level="error",
            log_event=f"{service_name}_service_error",
            service_name=service_name,
            **log_context,
        )

        # METRICS: Track external service errors with classification
        from src.infrastructure.observability.metrics_errors import (
            external_service_errors_total,
            external_service_timeouts_total,
        )

        # Classify error type from log_context or detail
        error_type = log_context.get("error_type", self._infer_error_type(detail))

        external_service_errors_total.labels(service_name=service_name, error_type=error_type).inc()

        # Track timeouts separately (critical for SLA monitoring)
        if error_type == "timeout":
            external_service_timeouts_total.labels(service_name=service_name).inc()

    @staticmethod
    def _infer_error_type(detail: str | None) -> str:
        """
        Infer error type from error detail message.

        Error taxonomy:
        - timeout: Connection timeout, request timeout
        - unauthorized: 401/403, invalid credentials
        - rate_limit: 429 Too Many Requests
        - not_found: 404 Not Found
        - api_error: 500+ errors from external service
        - unknown: Other errors

        Args:
            detail: Error detail message

        Returns:
            Error type for metrics labeling
        """
        if not detail:
            return "unknown"

        detail_lower = detail.lower()

        if "timeout" in detail_lower or "timed out" in detail_lower:
            return "timeout"
        elif "unauthorized" in detail_lower or "forbidden" in detail_lower:
            return "unauthorized"
        elif "rate limit" in detail_lower or "too many requests" in detail_lower:
            return "rate_limit"
        elif "not found" in detail_lower:
            return "not_found"
        elif (
            "api error" in detail_lower
            or "server error" in detail_lower
            or "service unavailable" in detail_lower
        ):
            return "api_error"
        else:
            return "unknown"


class DatabasePoolExhaustedError(BaseAPIException):
    """
    Database connection pool exhausted error.

    Raised when the application cannot obtain a database connection within
    the configured timeout (pool_timeout). This indicates resource exhaustion
    and should be handled gracefully with a user-friendly message.

    Root causes:
    - Too many concurrent requests vs pool size
    - Connection leaks (sessions not properly closed)
    - Long-running transactions holding connections
    - Slow queries blocking the pool

    Solution: Increase pool_size/max_overflow or investigate connection leaks.
    """

    def __init__(
        self,
        detail: str | None = None,
        operation: str = "database_operation",
        **log_context: Any,
    ) -> None:
        detail = detail or (
            "Service temporarily unavailable due to high load. " "Please retry in a few seconds."
        )

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            log_level="error",
            log_event="database_pool_exhausted",
            operation=operation,
            **log_context,
        )


# ============================================================================
# Helper Functions - Authentication & Authorization
# ============================================================================


def raise_invalid_credentials(email: str | None = None) -> NoReturn:
    """
    Raise authentication error for invalid credentials.

    Security: Generic message prevents user enumeration (OWASP).

    Args:
        email: Email attempted (optional, for logging only)

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    log_context = {"email": email} if email else {}
    raise AuthenticationError(detail="Invalid credentials", **log_context)


def raise_token_invalid(token_type: str = "token") -> NoReturn:
    """
    Raise authentication error for invalid or expired token.

    Args:
        token_type: Type of token (access, refresh, verification, reset)

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    raise AuthenticationError(
        detail=f"Invalid or expired {token_type}",
        token_type=token_type,
    )


def raise_token_already_used(
    token_type: str = "token",
    language: "SupportedLanguage" = "fr",
) -> NoReturn:
    """
    Raise authentication error for already used token (single-use tokens).

    Used for email verification and password reset tokens in PROD.
    Provides user-friendly message suggesting to request a new link.

    Args:
        token_type: Type of token (verification, password_reset)
        language: User language for i18n message (default: en)

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    from src.core.i18n_api_messages import APIMessages

    raise AuthenticationError(
        detail=APIMessages.token_already_used(language),
        token_type=token_type,
        reason="token_already_used",
    )


def raise_session_invalid() -> NoReturn:
    """
    Raise authentication error for invalid or expired session.

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    raise AuthenticationError(detail="Session invalid or expired")


def raise_user_not_authenticated() -> NoReturn:
    """
    Raise authentication error when user is not authenticated.

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    raise AuthenticationError(detail="Authentication required")


def raise_permission_denied(
    action: str | None = None,
    resource_type: str | None = None,
    user_id: UUID | None = None,
    resource_id: UUID | None = None,
    details: str | None = None,
) -> NoReturn:
    """
    Raise authorization error when user lacks permissions.

    Args:
        action: Action attempted (read, update, delete)
        resource_type: Type of resource (user, connector, conversation)
        user_id: User attempting the action (for audit logging)
        resource_id: Resource being accessed (for audit logging)
        details: Additional context about why permission was denied

    Raises:
        AuthorizationError: 403 Forbidden
    """
    detail = "Not authorized to access this resource"

    if action and resource_type:
        detail = f"Not authorized to {action} {resource_type}"

    if details:
        detail = f"{detail}. {details}"

    log_context = {}
    if user_id:
        log_context[FIELD_USER_ID] = str(user_id)
    if resource_id:
        log_context["resource_id"] = str(resource_id)
    if action:
        log_context["action"] = action
    if resource_type:
        log_context["resource_type"] = resource_type

    raise AuthorizationError(detail=detail, **log_context)


def raise_admin_required(user_id: UUID | None = None) -> NoReturn:
    """
    Raise authorization error when admin role is required.

    Args:
        user_id: User attempting the action (for audit logging)

    Raises:
        AuthorizationError: 403 Forbidden
    """
    log_context = {FIELD_USER_ID: str(user_id)} if user_id else {}
    raise AuthorizationError(detail="Admin privileges required", **log_context)


def raise_user_inactive(user_id: UUID) -> NoReturn:
    """
    Raise authorization error when user account is inactive.

    Args:
        user_id: Inactive user ID

    Raises:
        AuthorizationError: 403 Forbidden
    """
    raise AuthorizationError(
        detail="User account is inactive",
        user_id=str(user_id),
    )


def raise_user_not_verified(user_id: UUID) -> NoReturn:
    """
    Raise authorization error when user email is not verified.

    Args:
        user_id: Unverified user ID

    Raises:
        AuthorizationError: 403 Forbidden
    """
    raise AuthorizationError(
        detail="Email verification required",
        user_id=str(user_id),
    )


# ============================================================================
# Helper Functions - Resource Not Found
# ============================================================================


def raise_user_not_found(user_id: UUID | str) -> NoReturn:
    """
    Raise 404 error when user is not found.

    Args:
        user_id: User UUID or email

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="user",
        resource_id=user_id,
    )


def raise_connector_not_found(connector_id: UUID) -> NoReturn:
    """
    Raise 404 error when connector is not found.

    Args:
        connector_id: Connector UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="connector",
        resource_id=connector_id,
    )


def raise_conversation_not_found(conversation_id: UUID) -> NoReturn:
    """
    Raise 404 error when conversation is not found.

    Args:
        conversation_id: Conversation UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="conversation",
        resource_id=conversation_id,
    )


def raise_message_not_found(message_id: UUID) -> NoReturn:
    """
    Raise 404 error when message is not found.

    Args:
        message_id: Message UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="message",
        resource_id=message_id,
    )


# ============================================================================
# Helper Functions - Resource Conflicts
# ============================================================================


def raise_email_already_exists(email: str) -> NoReturn:
    """
    Raise 409 conflict error when email is already registered.

    Args:
        email: Email address

    Raises:
        ResourceConflictError: 409 Conflict
    """
    raise ResourceConflictError(
        resource_type="user",
        detail="Email already registered",
        email=email,
    )


def raise_connector_already_exists(
    user_id: UUID,
    connector_type: str,
) -> NoReturn:
    """
    Raise 409 conflict error when connector already exists for user.

    Args:
        user_id: User UUID
        connector_type: Connector type (gmail, google_drive, etc.)

    Raises:
        ResourceConflictError: 409 Conflict
    """
    raise ResourceConflictError(
        resource_type="connector",
        detail=f"{connector_type.capitalize()} connector already exists",
        user_id=str(user_id),
        connector_type=connector_type,
    )


# ============================================================================
# Helper Functions - Validation Errors
# ============================================================================


def raise_invalid_input(detail: str, **context: Any) -> NoReturn:
    """
    Raise 400 validation error for invalid input data.

    Args:
        detail: Specific validation error message
        **context: Additional context for logging

    Raises:
        ValidationError: 400 Bad Request
    """
    raise ValidationError(detail=detail, **context)


def raise_oauth_state_mismatch(
    user_id: UUID,
    connector_type: str,
) -> NoReturn:
    """
    Raise 400 validation error for OAuth state mismatch (CSRF protection).

    Args:
        user_id: User UUID
        connector_type: Connector type

    Raises:
        ValidationError: 400 Bad Request
    """
    raise ValidationError(
        detail="OAuth state mismatch",
        user_id=str(user_id),
        connector_type=connector_type,
    )


def raise_oauth_flow_failed(
    connector_type: str,
    error: str,
) -> NoReturn:
    """
    Raise 400 validation error when OAuth flow fails.

    Args:
        connector_type: Connector type
        error: Error message from OAuth provider

    Raises:
        ValidationError: 400 Bad Request
    """
    raise ValidationError(
        detail=f"OAuth flow failed: {error}",
        connector_type=connector_type,
        oauth_error=error,
    )


# ============================================================================
# Helper Functions - External Services
# ============================================================================


def raise_google_api_error(
    error_type: str,
    detail: str | None = None,
) -> NoReturn:
    """
    Raise external service error for Google API failures.

    Args:
        error_type: Error type (api_error, unauthorized, etc.)
        detail: Error detail message

    Raises:
        ExternalServiceError: 503 Service Unavailable
    """
    raise ExternalServiceError(
        service_name="google_api",
        detail=detail or "Google API error",
        error_type=error_type,
    )


def raise_llm_service_error(
    model_name: str,
    error: str,
) -> NoReturn:
    """
    Raise external service error for LLM service failures.

    Args:
        model_name: LLM model name (gpt-4.1-mini, gpt-4-turbo, etc.)
        error: Error message

    Raises:
        ExternalServiceError: 503 Service Unavailable
    """
    raise ExternalServiceError(
        service_name="llm_service",
        detail=f"LLM service error: {error}",
        model_name=model_name,
    )


# ============================================================================
# Security Helper - OWASP Enumeration Prevention
# ============================================================================


def raise_not_found_or_unauthorized(
    resource_type: str,
    resource_id: UUID | None = None,
) -> NoReturn:
    """
    Raise 404 error for both "not found" and "not authorized" cases.

    Security: Prevents user enumeration attacks by returning same error
    for both scenarios (OWASP recommendation).

    Use this when:
    - User tries to access another user's private resource
    - Resource doesn't exist

    Args:
        resource_type: Type of resource (user, connector, conversation)
        resource_id: Resource UUID (for audit logging only)

    Raises:
        ResourceNotFoundError: 404 Not Found

    Example:
        >>> # Instead of:
        >>> if not connector:
        >>>     raise_connector_not_found(connector_id)
        >>> if connector.user_id != current_user.id:
        >>>     raise_permission_denied()
        >>>
        >>> # Use this:
        >>> if not connector or connector.user_id != current_user.id:
        >>>     raise_not_found_or_unauthorized("connector", connector_id)
    """
    raise ResourceNotFoundError(
        resource_type=resource_type,
        resource_id=resource_id,
    )


# ============================================================================
# Rate Limiting Errors
# ============================================================================


class RateLimitError(BaseAPIException):
    """429 Too Many Requests - Rate limit exceeded."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        retry_after: int,
        **kwargs: Any,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            log_event="rate_limit_exceeded",
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            **kwargs,
        )


def raise_rate_limit_exceeded(
    limit: int,
    window_seconds: int,
    retry_after: int,
) -> NoReturn:
    """
    Raise when rate limit is exceeded.

    Args:
        limit: Maximum number of requests allowed
        window_seconds: Time window in seconds
        retry_after: Seconds until rate limit resets

    Raises:
        RateLimitError: 429 Too Many Requests
    """
    raise RateLimitError(
        limit=limit,
        window_seconds=window_seconds,
        retry_after=retry_after,
    )


def raise_api_rate_limit_exceeded(endpoint: str, limit: int) -> NoReturn:
    """
    Raise when API endpoint rate limit is exceeded.

    Args:
        endpoint: API endpoint that was rate limited
        limit: Maximum requests allowed per minute

    Raises:
        RateLimitError: 429 Too Many Requests
    """
    raise RateLimitError(
        limit=limit,
        window_seconds=60,
        retry_after=60,
        endpoint=endpoint,
    )


# ============================================================================
# Cache/Redis Errors
# ============================================================================


class CacheError(BaseAPIException):
    """503 - Cache service unavailable."""

    def __init__(
        self,
        operation: str,
        detail: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.operation = operation

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail or f"Cache operation failed: {operation}",
            log_level="error",
            log_event="cache_error",
            operation=operation,
            **kwargs,
        )


def raise_redis_connection_error(operation: str) -> NoReturn:
    """
    Raise when Redis connection fails.

    Args:
        operation: Cache operation that failed (get, set, delete, etc.)

    Raises:
        CacheError: 503 Service Unavailable
    """
    raise CacheError(
        operation=operation,
        detail="Redis connection unavailable",
        service="redis",
    )


def raise_cache_operation_failed(operation: str, key: str) -> NoReturn:
    """
    Raise when cache operation fails.

    Args:
        operation: Cache operation that failed
        key: Cache key involved

    Raises:
        CacheError: 503 Service Unavailable
    """
    raise CacheError(
        operation=operation,
        key=key,
    )


# ============================================================================
# Database Errors
# ============================================================================


class DatabaseError(BaseAPIException):
    """500 - Database operation error."""

    def __init__(
        self,
        operation: str,
        detail: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.operation = operation

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail or f"Database operation failed: {operation}",
            log_level="error",
            log_event="database_error",
            operation=operation,
            **kwargs,
        )


def raise_database_error(operation: str, details: str) -> NoReturn:
    """
    Raise for generic database errors.

    Args:
        operation: Database operation that failed
        details: Error details

    Raises:
        DatabaseError: 500 Internal Server Error
    """
    raise DatabaseError(operation=operation, detail=details)


def raise_constraint_violation(constraint: str, resource_type: str) -> NoReturn:
    """
    Raise when database constraint is violated.

    Args:
        constraint: Constraint name
        resource_type: Type of resource

    Raises:
        DatabaseError: 500 Internal Server Error
    """
    raise DatabaseError(
        operation="constraint_check",
        detail=f"Constraint violation: {constraint} on {resource_type}",
        constraint=constraint,
        resource_type=resource_type,
    )


def raise_query_timeout(query_name: str) -> NoReturn:
    """
    Raise when database query times out.

    Args:
        query_name: Name of the query that timed out

    Raises:
        DatabaseError: 500 Internal Server Error
    """
    raise DatabaseError(
        operation="query",
        detail=f"Query timeout: {query_name}",
        query_name=query_name,
    )


# ============================================================================
# Business Logic Errors
# ============================================================================


class BusinessLogicError(BaseAPIException):
    """400 - Business rule violation."""

    def __init__(
        self,
        rule: str,
        detail: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.rule = rule

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail or f"Business rule violated: {rule}",
            log_level="warning",
            log_event="business_logic_error",
            rule=rule,
            **kwargs,
        )


def raise_invalid_state_transition(
    resource: str,
    current_state: str,
    attempted_state: str,
) -> NoReturn:
    """
    Raise when invalid state transition is attempted.

    Args:
        resource: Resource type
        current_state: Current state of the resource
        attempted_state: State transition attempted

    Raises:
        BusinessLogicError: 400 Bad Request
    """
    raise BusinessLogicError(
        rule="state_transition",
        detail=f"Cannot transition {resource} from {current_state} to {attempted_state}",
        resource=resource,
        current_state=current_state,
        attempted_state=attempted_state,
    )


def raise_feature_disabled(feature_name: str) -> NoReturn:
    """
    Raise when disabled feature is accessed.

    Args:
        feature_name: Name of the disabled feature

    Raises:
        BusinessLogicError: 400 Bad Request
    """
    raise BusinessLogicError(
        rule="feature_flag",
        detail=f"Feature disabled: {feature_name}",
        feature_name=feature_name,
    )


# ============================================================================
# Additional Resource Not Found Helpers
# ============================================================================


def raise_prompt_not_found(prompt_id: UUID) -> NoReturn:
    """
    Raise when prompt is not found.

    Args:
        prompt_id: Prompt UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="prompt",
        resource_id=prompt_id,
    )


def raise_memory_not_found(memory_id: UUID | str) -> NoReturn:
    """
    Raise when memory is not found.

    Args:
        memory_id: Memory UUID or string ID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="memory",
        resource_id=memory_id,
    )


def raise_notification_not_found(notification_id: UUID) -> NoReturn:
    """
    Raise when notification is not found.

    Args:
        notification_id: Notification UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="notification",
        resource_id=notification_id,
    )


def raise_reminder_not_found(reminder_id: UUID) -> NoReturn:
    """
    Raise when reminder is not found.

    Args:
        reminder_id: Reminder UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="reminder",
        resource_id=reminder_id,
    )


# ============================================================================
# Validation Helpers
# ============================================================================


def raise_invalid_connector_config(
    connector_type: str,
    field: str,
    reason: str,
) -> NoReturn:
    """
    Raise when connector configuration is invalid.

    Args:
        connector_type: Type of connector (google_calendar, gmail, etc.)
        field: Field that is invalid
        reason: Reason for validation failure

    Raises:
        ValidationError: 400 Bad Request
    """
    raise ValidationError(
        detail=f"Invalid {connector_type} configuration: {field} - {reason}",
        connector_type=connector_type,
        field=field,
        reason=reason,
    )


# ============================================================================
# Memory Store Errors
# ============================================================================


class MemoryStoreError(BaseAPIException):
    """500 - Memory store operation error."""

    def __init__(
        self,
        operation: str,
        detail: str,
        memory_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.operation = operation

        log_context = {"operation": operation, **kwargs}
        if memory_id:
            log_context["memory_id"] = memory_id

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            log_event="memory_store_error",
            **log_context,
        )


def raise_memory_store_error(
    operation: str,
    detail: str,
    memory_id: str | None = None,
) -> NoReturn:
    """
    Raise when a memory store operation fails.

    Args:
        operation: Operation that failed (retrieve, create, update, delete, etc.)
        detail: User-facing error message
        memory_id: Optional memory ID involved

    Raises:
        MemoryStoreError: 500 Internal Server Error
    """
    raise MemoryStoreError(
        operation=operation,
        detail=detail,
        memory_id=memory_id,
    )


class HybridSearchError(BaseAPIException):
    """500 - Hybrid memory search operation error."""

    def __init__(
        self,
        detail: str = "Hybrid search failed",
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            log_event="hybrid_search_error",
            **log_context,
        )


def raise_hybrid_search_error(detail: str, **context: Any) -> NoReturn:
    """
    Raise when hybrid memory search fails.

    Args:
        detail: Error detail message
        **context: Additional context for logging

    Raises:
        HybridSearchError: 500 Internal Server Error
    """
    raise HybridSearchError(detail=detail, **context)


# ============================================================================
# Connector-Specific Errors
# ============================================================================


class ConnectorValidationError(BaseAPIException):
    """422 - Connector preferences validation error with structured errors."""

    def __init__(
        self,
        errors: list[dict[str, str]],
        connector_type: str | None = None,
        **log_context: Any,
    ) -> None:
        # Format as {"errors": [...]} for frontend compatibility
        detail_dict = {"errors": errors}

        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(detail_dict),  # BaseAPIException expects str
            log_level="warning",
            log_event="connector_validation_failed",
            connector_type=connector_type,
            error_count=len(errors),
            **log_context,
        )
        # Override detail with dict for JSON response
        self.detail = detail_dict  # type: ignore[assignment]


def raise_connector_type_no_preferences(connector_type: str) -> NoReturn:
    """
    Raise 404 error when connector type doesn't support preferences.

    Args:
        connector_type: Connector type (gmail, google_drive, etc.)

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="connector_preferences",
        detail=f"Connector type '{connector_type}' does not support preferences",
        connector_type=connector_type,
    )


def raise_connector_validation_errors(
    errors: list[dict[str, str]],
    connector_type: str | None = None,
) -> NoReturn:
    """
    Raise 422 validation error with structured error list.

    Args:
        errors: List of error dicts with 'field' and 'message' keys
        connector_type: Optional connector type for context

    Raises:
        ConnectorValidationError: 422 Unprocessable Entity
    """
    raise ConnectorValidationError(
        errors=errors,
        connector_type=connector_type,
    )


def raise_configuration_missing(service: str, field: str) -> NoReturn:
    """
    Raise 503 error when required configuration is missing.

    Args:
        service: Service name (google_api, google_places, etc.)
        field: Configuration field that is missing

    Raises:
        ExternalServiceError: 503 Service Unavailable
    """
    raise ExternalServiceError(
        service_name=service,
        detail=f"{service} configuration missing: {field}",
        error_type="configuration_missing",
        field=field,
    )


def raise_service_credentials_not_found(service: str, user_id: str) -> NoReturn:
    """
    Raise 404 error when service credentials are not found for user.

    Args:
        service: Service name (google_places, google_drive, etc.)
        user_id: User ID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type=f"{service}_credentials",
        detail=f"{service} credentials not configured for user",
        user_id=user_id,
    )


def raise_auth_token_missing(service: str) -> NoReturn:
    """
    Raise 401 error when authentication token is missing or invalid.

    Args:
        service: Service name (google_places, google_drive, etc.)

    Raises:
        AuthenticationError: 401 Unauthorized
    """
    raise AuthenticationError(
        detail=f"{service} access token not available",
        service=service,
    )


def raise_external_service_fetch_error(
    service: str,
    resource: str,
    status_code: int,
) -> NoReturn:
    """
    Raise error when external service fetch fails.

    Args:
        service: Service name (google_drive, google_places, etc.)
        resource: Resource being fetched (thumbnail, photo, etc.)
        status_code: HTTP status code from external service

    Raises:
        ExternalServiceError: 503 Service Unavailable
    """
    raise ExternalServiceError(
        service_name=service,
        detail=f"Failed to fetch {resource} from {service}",
        error_type="fetch_error",
        upstream_status_code=status_code,
    )


def raise_external_service_connection_error(service: str) -> NoReturn:
    """
    Raise 503 error when connection to external service fails.

    Args:
        service: Service name (google_drive, google_places, etc.)

    Raises:
        ExternalServiceError: 503 Service Unavailable
    """
    raise ExternalServiceError(
        service_name=service,
        detail=f"Failed to connect to {service}",
        error_type="connection_error",
    )


class InternalServerError(BaseAPIException):
    """500 - Internal server error for unexpected failures."""

    def __init__(
        self,
        detail: str,
        error_type: str | None = None,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            log_event="internal_server_error",
            error_type=error_type,
            **log_context,
        )


def raise_internal_error(detail: str, error_type: str | None = None) -> NoReturn:
    """
    Raise 500 internal server error for unexpected failures.

    Args:
        detail: Error detail message
        error_type: Optional error type for metrics/logging

    Raises:
        InternalServerError: 500 Internal Server Error
    """
    raise InternalServerError(
        detail=detail,
        error_type=error_type,
    )


# ============================================================================
# Conversation-Specific Errors
# ============================================================================


def raise_no_active_conversation(detail: str) -> NoReturn:
    """
    Raise 404 error when user has no active conversation.

    Args:
        detail: User-facing error message

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="conversation",
        detail=detail,
    )


# ============================================================================
# Notification-Specific Errors
# ============================================================================


def raise_push_token_not_found(user_id: UUID | str) -> NoReturn:
    """
    Raise 404 error when push notification token is not found.

    Args:
        user_id: User UUID or string

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="push_token",
        detail="Token not found or does not belong to user",
        user_id=str(user_id),
    )


class ForbiddenError(BaseAPIException):
    """403 - Forbidden access to resource or feature."""

    def __init__(
        self,
        detail: str,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            log_level="warning",
            log_event="forbidden_access",
            **log_context,
        )


def raise_test_endpoint_disabled() -> NoReturn:
    """
    Raise 403 error when test endpoint is accessed in production.

    Raises:
        ForbiddenError: 403 Forbidden
    """
    raise ForbiddenError(
        detail="Test endpoint not available in production",
        reason="production_mode",
    )


def raise_user_id_mismatch() -> NoReturn:
    """
    Raise 403 error when user ID in request doesn't match authenticated user.

    Raises:
        ForbiddenError: 403 Forbidden
    """
    raise ForbiddenError(
        detail="User ID mismatch - you can only access your own resources",
        reason="user_id_mismatch",
    )


# ============================================================================
# LLM Pricing Errors
# ============================================================================


def raise_pricing_already_exists(model_name: str) -> NoReturn:
    """
    Raise 409 conflict when LLM pricing already exists for model.

    Args:
        model_name: LLM model name

    Raises:
        ResourceConflictError: 409 Conflict
    """
    raise ResourceConflictError(
        resource_type="llm_pricing",
        detail=f"Pricing already exists for model: {model_name}",
        model_name=model_name,
    )


def raise_pricing_not_found(identifier: str) -> NoReturn:
    """
    Raise 404 when LLM pricing is not found.

    Args:
        identifier: Model name or pricing ID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="llm_pricing",
        detail=f"Pricing not found: {identifier}",
        identifier=identifier,
    )


# ============================================================================
# Interest-Specific Errors
# ============================================================================


def raise_interest_not_found(interest_id: UUID) -> NoReturn:
    """
    Raise 404 when interest is not found.

    Args:
        interest_id: Interest UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="interest",
        resource_id=interest_id,
    )


def raise_interest_already_exists(user_id: UUID, topic: str) -> NoReturn:
    """
    Raise 409 conflict when interest already exists for user.

    Args:
        user_id: User UUID
        topic: Interest topic

    Raises:
        ResourceConflictError: 409 Conflict
    """
    raise ResourceConflictError(
        resource_type="interest",
        detail="Interest with this topic already exists",
        user_id=str(user_id),
        topic=topic[:50],
    )


class InterestStoreError(BaseAPIException):
    """500 - Interest store operation error."""

    def __init__(
        self,
        operation: str,
        detail: str,
        interest_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.operation = operation

        log_context = {"operation": operation, **kwargs}
        if interest_id:
            log_context["interest_id"] = interest_id

        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            log_event="interest_store_error",
            **log_context,
        )


def raise_interest_store_error(
    operation: str,
    detail: str,
    interest_id: str | None = None,
) -> NoReturn:
    """
    Raise when an interest store operation fails.

    Args:
        operation: Operation that failed (list, create, update, delete, feedback)
        detail: User-facing error message
        interest_id: Optional interest ID involved

    Raises:
        InterestStoreError: 500 Internal Server Error
    """
    raise InterestStoreError(
        operation=operation,
        detail=detail,
        interest_id=interest_id,
    )


# ============================================================================
# Voice STT (Speech-to-Text) Errors
# ============================================================================


class STTError(BaseAPIException):
    """500 - Speech-to-text transcription error."""

    def __init__(
        self,
        detail: str = "Transcription failed",
        operation: str = "transcribe",
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            log_event="stt_error",
            operation=operation,
            **log_context,
        )


class STTModelNotFoundError(BaseAPIException):
    """503 - STT model not found or not loaded."""

    def __init__(
        self,
        model_path: str,
        detail: str | None = None,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail or f"STT model not found at {model_path}",
            log_level="error",
            log_event="stt_model_not_found",
            model_path=model_path,
            **log_context,
        )


class STTAudioTooLongError(BaseAPIException):
    """400 - Audio duration exceeds maximum allowed."""

    def __init__(
        self,
        duration_seconds: float,
        max_seconds: int,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio too long: {duration_seconds:.1f}s exceeds maximum {max_seconds}s",
            log_level="warning",
            log_event="stt_audio_too_long",
            duration_seconds=duration_seconds,
            max_seconds=max_seconds,
            **log_context,
        )


def raise_stt_error(
    detail: str,
    operation: str = "transcribe",
    **context: Any,
) -> NoReturn:
    """
    Raise when STT transcription fails.

    Args:
        detail: Error detail message
        operation: Operation that failed (transcribe, decode, etc.)
        **context: Additional context for logging

    Raises:
        STTError: 500 Internal Server Error
    """
    raise STTError(detail=detail, operation=operation, **context)


def raise_stt_model_not_found(model_path: str) -> NoReturn:
    """
    Raise when STT model is not found.

    Args:
        model_path: Path where model was expected

    Raises:
        STTModelNotFoundError: 503 Service Unavailable
    """
    raise STTModelNotFoundError(model_path=model_path)


def raise_stt_audio_too_long(
    duration_seconds: float,
    max_seconds: int,
) -> NoReturn:
    """
    Raise when audio exceeds maximum duration.

    Args:
        duration_seconds: Actual audio duration
        max_seconds: Maximum allowed duration

    Raises:
        STTAudioTooLongError: 400 Bad Request
    """
    raise STTAudioTooLongError(
        duration_seconds=duration_seconds,
        max_seconds=max_seconds,
    )


# ============================================================================
# WebSocket Authentication Errors
# ============================================================================


class WebSocketAuthError(BaseAPIException):
    """401 - WebSocket authentication failed."""

    def __init__(
        self,
        detail: str = "WebSocket authentication failed",
        reason: str = "invalid_ticket",
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            log_level="warning",
            log_event="websocket_auth_failed",
            reason=reason,
            **log_context,
        )


class WebSocketRateLimitError(BaseAPIException):
    """429 - WebSocket connection rate limited."""

    def __init__(
        self,
        user_id: str,
        limit: int,
        window_seconds: int,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limited: max {limit} connections per {window_seconds}s",
            log_level="warning",
            log_event="websocket_rate_limited",
            user_id=user_id,
            limit=limit,
            window_seconds=window_seconds,
            **log_context,
        )


def raise_websocket_auth_error(
    reason: str = "invalid_ticket",
    detail: str | None = None,
) -> NoReturn:
    """
    Raise when WebSocket authentication fails.

    Args:
        reason: Reason for failure (invalid_ticket, expired, already_used)
        detail: Optional custom detail message

    Raises:
        WebSocketAuthError: 401 Unauthorized
    """
    raise WebSocketAuthError(
        detail=detail or "WebSocket authentication failed",
        reason=reason,
    )


def raise_websocket_rate_limit(
    user_id: str,
    limit: int,
    window_seconds: int,
) -> NoReturn:
    """
    Raise when WebSocket connection is rate limited.

    Args:
        user_id: User who was rate limited
        limit: Max connections allowed
        window_seconds: Rate limit window

    Raises:
        WebSocketRateLimitError: 429 Too Many Requests
    """
    raise WebSocketRateLimitError(
        user_id=user_id,
        limit=limit,
        window_seconds=window_seconds,
    )


# =============================================================================
# JOURNALS (Personal Journals — Carnets de Bord)
# =============================================================================


def raise_journal_not_found(entry_id: UUID) -> NoReturn:
    """
    Raise 404 when journal entry is not found.

    Args:
        entry_id: Journal entry UUID

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="journal_entry",
        resource_id=entry_id,
    )


def raise_journal_size_exceeded(
    current_chars: int,
    max_chars: int,
) -> NoReturn:
    """
    Raise 400 when journal size limit would be exceeded.

    Args:
        current_chars: Current total characters
        max_chars: Maximum allowed characters

    Raises:
        ValidationError: 400 Bad Request
    """
    raise ValidationError(
        detail=(
            f"Journal size limit exceeded: {current_chars} / {max_chars} characters. "
            "Delete or summarize entries to free space."
        ),
        current_chars=current_chars,
        max_chars=max_chars,
    )
