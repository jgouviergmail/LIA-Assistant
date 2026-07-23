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

Structure (ADR-124, file-size ratchet):
    - ``src.core._exceptions_base`` — ``BaseAPIException`` (internal module)
    - ``src.core.exceptions_domains`` — domain-specific families (memory,
      interests, STT, WebSocket)
    - this module — generic taxonomy + raisers, and the façade re-exporting
      every name above (consumers only ever import from here)

ADR Reference: ADR-002 (Unified Error Handling), ADR-124 (rule #18 phase 2)
"""

from typing import TYPE_CHECKING, Any, NoReturn
from uuid import UUID

from fastapi import status

from src.core._exceptions_base import BaseAPIException as BaseAPIException
from src.core.exceptions_domains import (
    HybridSearchError as HybridSearchError,
)
from src.core.exceptions_domains import (
    InterestStoreError as InterestStoreError,
)
from src.core.exceptions_domains import (
    MemoryStoreError as MemoryStoreError,
)
from src.core.exceptions_domains import (
    STTAudioTooLongError as STTAudioTooLongError,
)
from src.core.exceptions_domains import (
    STTError as STTError,
)
from src.core.exceptions_domains import (
    STTModelNotFoundError as STTModelNotFoundError,
)
from src.core.exceptions_domains import (
    WebSocketAuthError as WebSocketAuthError,
)
from src.core.exceptions_domains import (
    WebSocketRateLimitError as WebSocketRateLimitError,
)
from src.core.exceptions_domains import (
    raise_hybrid_search_error as raise_hybrid_search_error,
)
from src.core.exceptions_domains import (
    raise_interest_store_error as raise_interest_store_error,
)
from src.core.exceptions_domains import (
    raise_memory_store_error as raise_memory_store_error,
)
from src.core.exceptions_domains import (
    raise_stt_audio_too_long as raise_stt_audio_too_long,
)
from src.core.exceptions_domains import (
    raise_stt_error as raise_stt_error,
)
from src.core.exceptions_domains import (
    raise_stt_model_not_found as raise_stt_model_not_found,
)
from src.core.exceptions_domains import (
    raise_websocket_auth_error as raise_websocket_auth_error,
)
from src.core.exceptions_domains import (
    raise_websocket_rate_limit as raise_websocket_rate_limit,
)
from src.core.field_names import FIELD_USER_ID

if TYPE_CHECKING:
    from src.core.i18n_api_messages import SupportedLanguage


# ============================================================================
# Custom Exception Classes
# ============================================================================


class AuthenticationError(BaseAPIException):
    """Authentication failed - invalid credentials or token."""

    def __init__(
        self,
        detail: str = "Invalid credentials",
        headers: dict[str, str] | None = None,
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            log_level="warning",
            log_event="authentication_failed",
            headers=headers,
            **log_context,
        )


class AuthorizationError(BaseAPIException):
    """Authorization failed - insufficient permissions.

    ``detail`` may be a structured dict for typed 403s the client must
    distinguish (e.g. the step-up contract ``{"error": "step_up_required"}``).
    """

    def __init__(
        self,
        detail: str | dict[str, Any] = "Not authorized to access this resource",
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
    """Resource conflict - duplicate or constraint violation.

    ``detail`` may be a structured dict when the edge exposes a
    machine-readable payload (e.g. the active-run lock's
    ``{"error": "run_in_progress", "active_run": ...}`` — ADR-117/124).
    """

    def __init__(
        self,
        resource_type: str,
        detail: str | dict[str, Any] | None = None,
        **log_context: Any,
    ) -> None:
        fallback_detail = f"{resource_type.capitalize()} already exists"

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail if isinstance(detail, str) else fallback_detail,
            log_level="warning",
            log_event=f"{resource_type}_conflict",
            resource_type=resource_type,
            **log_context,
        )
        if isinstance(detail, dict):
            # Keep the exact structured JSON body on the wire (same pattern
            # as ConnectorValidationError: str for the base/logging, dict out).
            self.detail = detail  # type: ignore[assignment]


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


class StructuredValidationError(BaseAPIException):
    """422 with a Pydantic-style structured detail (type/loc/msg/input/ctx).

    Mirrors FastAPI's ``RequestValidationError`` item shape so the frontend
    can render actionable error toasts ("did you mean" hints). Used by the
    admin LLM-config write path (reasoning matrix validation) and any
    endpoint that must reject a field with machine-readable context.
    """

    def __init__(
        self,
        error_type: str,
        loc: list[str],
        msg: str,
        input_value: Any,
        ctx: dict[str, Any],
        **log_context: Any,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=msg,
            log_level="warning",
            log_event="structured_validation_failed",
            validation_type=error_type,
            **log_context,
        )
        # Keep the exact structured JSON body on the wire (same pattern as
        # ConnectorValidationError: str for the base/logging, dict out).
        self.detail = {  # type: ignore[assignment]
            "type": error_type,
            "loc": loc,
            "msg": msg,
            "input": input_value,
            "ctx": ctx,
        }


def raise_structured_validation_error(
    error_type: str,
    loc: list[str],
    msg: str,
    input_value: Any,
    ctx: dict[str, Any],
) -> NoReturn:
    """
    Raise 422 with a Pydantic-style structured detail dict.

    Args:
        error_type: Machine-readable error kind (e.g. "invalid_reasoning_effort")
        loc: Field location path (e.g. ["body", "reasoning_effort"])
        msg: Human-readable message
        input_value: The rejected input, serialized for the payload
        ctx: Machine-readable context for frontend hints

    Raises:
        StructuredValidationError: 422 Unprocessable Entity
    """
    raise StructuredValidationError(
        error_type=error_type,
        loc=loc,
        msg=msg,
        input_value=input_value,
        ctx=ctx,
    )


class UnprocessableEntityError(BaseAPIException):
    """422 - Semantically invalid input (plain-string detail)."""

    def __init__(self, detail: str, **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
            log_level="warning",
            log_event="unprocessable_entity",
            **log_context,
        )


def raise_unprocessable_entity(detail: str, **context: Any) -> NoReturn:
    """
    Raise 422 for semantically invalid input (plain-string detail).

    Args:
        detail: Specific validation error message
        **context: Additional context for logging

    Raises:
        UnprocessableEntityError: 422 Unprocessable Entity
    """
    raise UnprocessableEntityError(detail=detail, **context)


class PayloadTooLargeError(BaseAPIException):
    """413 - Request payload exceeds a configured size limit."""

    def __init__(self, detail: str, **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=detail,
            log_level="warning",
            log_event="payload_too_large",
            **log_context,
        )


def raise_payload_too_large(detail: str, **context: Any) -> NoReturn:
    """
    Raise 413 when a request payload exceeds a configured size limit.

    Args:
        detail: Error message carrying the actual/allowed sizes
        **context: Additional context for logging

    Raises:
        PayloadTooLargeError: 413 Request Entity Too Large
    """
    raise PayloadTooLargeError(detail=detail, **context)


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
        headers: dict[str, str] | None = None,
        **log_context: Any,
    ) -> None:
        detail = detail or f"{service_name} service unavailable"

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            log_level="error",
            log_event=f"{service_name}_service_error",
            headers=headers,
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
    log_context: dict[str, Any] = {"email": email} if email else {}
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


def raise_bearer_auth_failed(detail: str, **context: Any) -> NoReturn:
    """
    Raise 401 with the RFC 7235 ``WWW-Authenticate: Bearer`` challenge.

    For token-based (non-session) edges — e.g. the health-metrics ingestion
    Bearer tokens — where the client must be told which auth scheme to use.

    Args:
        detail: User-facing error message
        **context: Additional context for logging

    Raises:
        AuthenticationError: 401 Unauthorized (+ WWW-Authenticate: Bearer)
    """
    raise AuthenticationError(
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
        **context,
    )


def raise_step_up_required() -> NoReturn:
    """
    Raise the typed 403 demanding a recent step-up re-authentication.

    Contract (security program D1, Lot 3): NEVER a plain 401 — the frontend
    api-client hard-redirects 401s to /login. The typed detail lets the
    client open the re-auth dialog and replay the original call.

    Raises:
        AuthorizationError: 403 Forbidden with ``detail.error = "step_up_required"``.
    """
    from src.core.constants import STEP_UP_ERROR_CODE

    raise AuthorizationError(
        detail={
            "error": STEP_UP_ERROR_CODE,
            "message": "Recent re-authentication required for this sensitive action",
        },
    )


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


def raise_scheduled_action_already_executing(action_id: UUID) -> NoReturn:
    """
    Raise 409 conflict when a scheduled action is already executing.

    Args:
        action_id: Scheduled action UUID

    Raises:
        ResourceConflictError: 409 Conflict
    """
    raise ResourceConflictError(
        resource_type="scheduled_action",
        detail="Action is already executing",
        action_id=str(action_id),
    )


def raise_run_in_progress(active_run: dict[str, Any] | None) -> NoReturn:
    """
    Raise 409 for the per-conversation active-run lock (ADR-117).

    One concurrent chat run per conversation: a second run attempt returns
    the structured payload the frontend uses to offer live-resume.

    Args:
        active_run: Metadata of the run holding the lock (or None if it
            vanished between the failed acquire and the lookup)

    Raises:
        ResourceConflictError: 409 Conflict with a structured detail dict
    """
    raise ResourceConflictError(
        resource_type="chat_run",
        detail={"error": "run_in_progress", "active_run": active_run},
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
    """429 Too Many Requests - Rate limit exceeded.

    ``detail`` may be a structured dict when the edge exposes a
    machine-readable payload (e.g. ``{"error": "rate_limit_exceeded", ...}``)
    and ``headers`` carries the RFC-standard ``Retry-After`` when the caller
    sets it — both keep legacy raw-HTTPException contracts byte-identical
    (ADR-124).
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        retry_after: int,
        detail: str | dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after

        fallback_detail = f"Rate limit exceeded: {limit} requests per {window_seconds}s"
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail if isinstance(detail, str) else fallback_detail,
            log_event="rate_limit_exceeded",
            headers=headers,
            limit=limit,
            window_seconds=window_seconds,
            retry_after=retry_after,
            **kwargs,
        )
        if isinstance(detail, dict):
            # Keep the exact structured JSON body on the wire (same pattern
            # as ConnectorValidationError: str for the base/logging, dict out).
            self.detail = detail  # type: ignore[assignment]


def raise_rate_limit_exceeded(
    limit: int,
    window_seconds: int,
    retry_after: int,
    detail: str | dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> NoReturn:
    """
    Raise when rate limit is exceeded.

    Args:
        limit: Maximum number of requests allowed
        window_seconds: Time window in seconds
        retry_after: Seconds until rate limit resets
        detail: Optional detail override — str, or dict for edges exposing a
            structured payload (kept byte-identical on the wire)
        headers: Optional response headers (e.g. ``{"Retry-After": "60"}``)

    Raises:
        RateLimitError: 429 Too Many Requests
    """
    raise RateLimitError(
        limit=limit,
        window_seconds=window_seconds,
        retry_after=retry_after,
        detail=detail,
        headers=headers,
    )


class UsageLimitExceededError(BaseAPIException):
    """Raised when a user exceeds their per-user usage limits (tokens, messages, cost)."""

    def __init__(
        self,
        limit_name: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.limit_name = limit_name
        self.reason = reason

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason or "Usage limit exceeded",
            log_event="usage_limit_exceeded",
            limit_name=limit_name or "unknown",
            **kwargs,
        )


def raise_usage_limit_exceeded(
    limit_name: str | None = None,
    reason: str | None = None,
) -> NoReturn:
    """
    Raise when a user exceeds their per-user usage limits.

    Args:
        limit_name: Which limit was exceeded (e.g., 'cycle_tokens', 'manual_block').
        reason: Human-readable reason for the block.

    Raises:
        UsageLimitExceededError: 429 Too Many Requests
    """
    raise UsageLimitExceededError(limit_name=limit_name, reason=reason)


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


def raise_admin_mcp_server_not_found(server_key: str) -> NoReturn:
    """
    Raise 404 when an admin MCP server key is unknown.

    Args:
        server_key: The admin MCP server key looked up in the client manager

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(
        resource_type="admin_mcp_server",
        detail=f"Admin MCP server '{server_key}' not found",
        server_key=server_key,
    )


def raise_llm_type_not_found(detail: str) -> NoReturn:
    """
    Raise 404 when an LLM type is unknown to the registry.

    Args:
        detail: User-facing message (the service's ValueError text, forwarded
            verbatim to keep the admin API contract)

    Raises:
        ResourceNotFoundError: 404 Not Found
    """
    raise ResourceNotFoundError(resource_type="llm_type", detail=detail)


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
# Connector-Specific Errors
# ============================================================================


class ConnectorAPIError(BaseAPIException):
    """Upstream connector API returned a non-retryable error, forwarded as-is.

    Raised by the connector client layer when the upstream provider (Google,
    Microsoft, etc.) returns an error response that is not handled by a more
    specific path (401 auth, 429 retry, 5xx retry where applicable). The
    upstream HTTP status code is forwarded unchanged so the external API
    contract is preserved end-to-end (a 403 from Google stays a 403).
    """

    def __init__(
        self,
        connector_type: str,
        status_code: int,
        detail: str,
        **log_context: Any,
    ) -> None:
        """
        Initialize connector API error.

        Args:
            connector_type: Connector type value (e.g. "google_gmail")
            status_code: Upstream HTTP status code, forwarded as-is (>= 400)
            detail: Error message (user-facing, no raw PII)
            **log_context: Additional context for structured logging
        """
        super().__init__(
            status_code=status_code,
            detail=detail,
            log_level="warning",
            log_event="connector_api_error",
            connector_type=connector_type,
            upstream_status_code=status_code,
            **log_context,
        )
        # Typed attributes so agent-side handlers can classify without
        # string matching (Lot 3 P3 — actionable connector error notices).
        self.connector_type = connector_type
        self.upstream_status_code = status_code


class ConnectorTokenExpiredError(ValidationError):
    """OAuth refresh rejected by the provider — the user must reconnect.

    Raised by ``ConnectorService._refresh_oauth_token`` when the token
    endpoint rejects the refresh (``invalid_grant`` = revoked or expired
    refresh token, or any non-200). Subclasses ``ValidationError`` on purpose:
    the HTTP contract (400) and every existing ``except ValidationError``
    remain intact, while agent-side handlers can now catch this specific
    class to surface an actionable "reconnect" notice in the chat.
    """

    def __init__(self, detail: str, connector_type: str, **log_context: Any) -> None:
        """Initialize with the connector that needs reconnecting.

        Args:
            detail: User-facing message (already localized upstream)
            connector_type: Connector type value (e.g. "google_gmail")
            **log_context: Additional context for structured logging
        """
        super().__init__(detail=detail, connector_type=connector_type, **log_context)
        self.connector_type = connector_type


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


def raise_invalid_webhook_signature(channel: str) -> NoReturn:
    """
    Raise 403 when an inbound webhook signature check fails.

    Args:
        channel: Channel whose webhook was rejected (e.g. "telegram")

    Raises:
        ForbiddenError: 403 Forbidden
    """
    raise ForbiddenError(
        detail="Invalid webhook signature",
        channel=channel,
        reason="invalid_webhook_signature",
    )


class GoneError(BaseAPIException):
    """410 - Resource or endpoint permanently removed.

    Accepts a structured dict detail for tombstone endpoints that return
    machine-readable migration guidance (e.g. the BFF ``/auth/refresh``
    removal).
    """

    def __init__(self, detail: str | dict[str, Any], **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=detail if isinstance(detail, str) else "Endpoint permanently removed",
            log_level="info",
            log_event="endpoint_gone",
            **log_context,
        )
        if isinstance(detail, dict):
            # Keep the exact structured JSON body on the wire (same pattern
            # as ConnectorValidationError: str for the base/logging, dict out).
            self.detail = detail  # type: ignore[assignment]


class BadGatewayError(BaseAPIException):
    """502 - Upstream service returned an invalid response or is unreachable.

    Distinct from ``ExternalServiceError`` (503, "try again later"): 502
    signals that THIS service acted as a gateway and the upstream failed —
    e.g. a user-configured MCP server that cannot complete an OAuth flow.
    """

    def __init__(self, detail: str, **log_context: Any) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
            log_level="error",
            log_event="bad_gateway",
            **log_context,
        )


def raise_bad_gateway(detail: str, **context: Any) -> NoReturn:
    """
    Raise 502 when an upstream dependency fails while acting as a gateway.

    Args:
        detail: User-facing error message
        **context: Additional context for logging

    Raises:
        BadGatewayError: 502 Bad Gateway
    """
    raise BadGatewayError(detail=detail, **context)


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
