"""
Centralized error handlers for OAuth and API client errors.

Phase 3.2.9: Generic error handling to eliminate duplication across API clients.

These handlers provide consistent error responses for common OAuth/API failures,
with proper logging, user-friendly messages, and automatic retry logic.

Error Categories:
1. OAuth Errors (401, invalid credentials)
2. Permission Errors (403, insufficient scopes)
3. Rate Limit Errors (429, quota exceeded)
4. Server Errors (5xx, temporary failures)
5. Network Errors (timeouts, connection failures)
6. OAuth Callback Errors (redirect handling) - Added Phase 3.2.10

Best Practices:
- Use handle_oauth_error() for 401 errors → invalidate connector
- Use handle_rate_limit_error() for 429/403 rate limit errors
- Use handle_insufficient_permissions() for 403 scope errors
- Use retry_with_exponential_backoff() decorator for 5xx errors
- Use handle_oauth_callback_error_redirect() for OAuth callback errors → redirect to frontend
- Log all errors with structured logging (Langfuse v3 compatible)

References:
- OAuth 2.1: https://oauth.net/2.1/
- Google API errors: https://developers.google.com/gmail/api/guides/handle-errors
- Tenacity (retry): https://tenacity.readthedocs.io/

Version: 1.1.0
Created: November 2025 (Gmail integration debugging session)
Updated: December 2025 (OAuth callback error refactoring)
"""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

import httpx
import structlog
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.field_names import FIELD_ERROR_TYPE
from src.core.i18n_api_messages import APIMessages
from src.core.oauth.exceptions import (
    OAuthFlowError,
    OAuthProviderError,
    OAuthStateValidationError,
    OAuthTokenExchangeError,
)
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.repository import ConnectorRepository

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# ============================================================================
# OAuth Errors (401)
# ============================================================================


async def handle_oauth_error(
    user_id: str,
    connector_type: ConnectorType,
    session: AsyncSession,
    *,
    error_detail: str | None = None,
) -> dict[str, Any]:
    """
    Handle OAuth authentication errors (401 Unauthorized).

    Automatically:
    1. Invalidates the connector in database (marks as failed)
    2. Logs the error with user context
    3. Returns user-friendly error response

    Args:
        user_id: User ID (UUID string)
        connector_type: Type of connector (ConnectorType enum)
        session: SQLAlchemy async session for DB operations
        error_detail: Optional detailed error message from API

    Returns:
        Error response dict with message and metadata

    Example:
        >>> try:
        ...     response = await gmail_api.list_messages()
        ... except httpx.HTTPStatusError as e:
        ...     if e.response.status_code == 401:
        ...         return await handle_oauth_error(
        ...             user_id=str(self.user_id),
        ...             connector_type=ConnectorType.GOOGLE_GMAIL,
        ...             session=self.session,
        ...             error_detail=e.response.json().get("error_description")
        ...         )

    Best Practices:
        - Always invalidate connector on 401 errors
        - Prompt user to reconnect OAuth in UI
        - Log error for security audit
        - Include connector_type for debugging
    """
    logger.error(
        "oauth_authentication_error",
        user_id=user_id,
        connector_type=connector_type.value,
        error_detail=error_detail,
    )

    # Invalidate connector in database
    repository = ConnectorRepository(session)

    try:
        # Get connector using repository method
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        connector = await repository.get_by_user_and_type(
            user_id=user_uuid,
            connector_type=connector_type,
        )

        if connector:
            # Mark as error by updating status directly
            connector.status = ConnectorStatus.ERROR
            connector.error_message = "OAuth authentication failed. Please reconnect."
            await session.flush()
            await session.refresh(connector)

            logger.info(
                "connector_invalidated_oauth_error",
                user_id=user_id,
                connector_id=str(connector.id),
                connector_type=connector_type.value,
            )
        else:
            logger.warning(
                "connector_not_found_oauth_error",
                user_id=user_id,
                connector_type=connector_type.value,
            )

    except Exception as e:
        logger.error(
            "failed_to_invalidate_connector",
            user_id=user_id,
            connector_type=connector_type.value,
            error=str(e),
            error_type=type(e).__name__,
        )

    # Return user-friendly error
    connector_name = connector_type.value.replace("_", " ").title()
    return {
        "success": False,
        "error": "authentication_error",
        "message": APIMessages.connector_auth_invalid(connector_name),
        "metadata": {
            FIELD_ERROR_TYPE: "OAuthError",
            "connector_type": connector_type.value,
            "requires_reconnect": True,
        },
    }


# ============================================================================
# OAuth Callback Errors (Redirect Handling)
# ============================================================================


class OAuthCallbackErrorCode(StrEnum):
    """
    Error codes for OAuth callback redirects to frontend.

    These codes are used in the URL query parameter `connector_error`
    to indicate the type of failure during OAuth flow.

    Frontend mapping:
    - oauth_failed: Generic OAuth error, prompt user to retry
    - invalid_state: CSRF token validation failed, possible attack or expired session
    - user_not_found: User ID in OAuth state doesn't exist in database
    - token_exchange_failed: Failed to exchange auth code for tokens
    - connector_disabled: Connector type is globally disabled by admin
    - user_inactive: User account is deactivated
    """

    OAUTH_FAILED = "oauth_failed"
    INVALID_STATE = "invalid_state"
    USER_NOT_FOUND = "user_not_found"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    CONNECTOR_DISABLED = "connector_disabled"
    USER_INACTIVE = "user_inactive"


def classify_oauth_callback_error(error: Exception) -> OAuthCallbackErrorCode:
    """
    Classify an OAuth callback exception into a frontend-friendly error code.

    Uses exception type hierarchy instead of string parsing for reliability.
    This replaces the fragile pattern of parsing str(e).lower() to determine error types.

    Args:
        error: The caught exception

    Returns:
        OAuthCallbackErrorCode for frontend redirect

    Example:
        >>> try:
        ...     await service.handle_gmail_callback_stateless(code, state)
        ... except Exception as e:
        ...     error_code = classify_oauth_callback_error(e)
        ...     return handle_oauth_callback_error_redirect(e, "gmail")
    """
    # OAuth-specific exceptions (from core/oauth/exceptions.py)
    if isinstance(error, OAuthStateValidationError):
        return OAuthCallbackErrorCode.INVALID_STATE

    if isinstance(error, OAuthTokenExchangeError):
        return OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED

    if isinstance(error, OAuthProviderError):
        return OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED

    # Core exceptions
    if isinstance(error, ResourceNotFoundError):
        # Check if it's a user not found error
        if hasattr(error, "resource_type") and error.resource_type == "user":
            return OAuthCallbackErrorCode.USER_NOT_FOUND
        return OAuthCallbackErrorCode.OAUTH_FAILED

    if isinstance(error, AuthorizationError):
        # User inactive or similar
        return OAuthCallbackErrorCode.USER_INACTIVE

    # Generic OAuth flow errors
    if isinstance(error, OAuthFlowError):
        # Check error_code attribute if available
        if hasattr(error, "error_code"):
            if error.error_code == "invalid_state":
                return OAuthCallbackErrorCode.INVALID_STATE
            if error.error_code == "token_exchange_failed":
                return OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED
        return OAuthCallbackErrorCode.OAUTH_FAILED

    # Fallback: generic OAuth failure
    return OAuthCallbackErrorCode.OAUTH_FAILED


def handle_oauth_callback_error_redirect(
    error: Exception,
    connector_type: str,
    error_code: OAuthCallbackErrorCode | None = None,
) -> RedirectResponse:
    """
    Create a redirect response for OAuth callback errors.

    Logs the error with full context and returns a redirect to frontend
    with appropriate error code. This eliminates the duplicated try/except
    blocks across all OAuth callback endpoints.

    Args:
        error: The caught exception
        connector_type: Type of connector (e.g., "gmail", "google_contacts", "google_calendar")
        error_code: Pre-classified error code (optional, will be inferred if None)

    Returns:
        RedirectResponse to frontend settings page with error parameter

    Example:
        >>> @router.get("/gmail/callback")
        ... async def gmail_oauth_callback(code: str, state: str, db: ...):
        ...     service = ConnectorService(db)
        ...     try:
        ...         connector = await service.handle_gmail_callback_stateless(code, state)
        ...         return RedirectResponse(url=f"{settings.frontend_url}/dashboard/settings?...")
        ...     except Exception as e:
        ...         return handle_oauth_callback_error_redirect(e, "gmail")
    """
    # Classify if not provided
    if error_code is None:
        error_code = classify_oauth_callback_error(error)

    # Log with full context for debugging
    logger.error(
        f"{connector_type}_oauth_callback_failed",
        error=str(error),
        error_type=type(error).__name__,
        error_code=error_code.value,
        exc_info=True,
    )

    # Build redirect URL to frontend settings page with error parameter
    redirect_url = (
        f"{settings.frontend_url}/dashboard/settings" f"?connector_error={error_code.value}"
    )

    return RedirectResponse(url=redirect_url, status_code=302)


# ============================================================================
# Permission Errors (403 Insufficient Permissions)
# ============================================================================


def handle_insufficient_permissions(
    connector_type: ConnectorType,
    required_scopes: list[str],
    *,
    operation: str | None = None,
) -> dict[str, Any]:
    """
    Handle insufficient OAuth permissions errors (403 Forbidden - insufficient scopes).

    Returns user-friendly error indicating missing scopes.

    Args:
        connector_type: Type of connector
        required_scopes: List of required OAuth scopes that are missing
        operation: Optional operation that failed (e.g., "send_email")

    Returns:
        Error response dict with message and metadata

    Example:
        >>> if "gmail.send" not in current_scopes:
        ...     return handle_insufficient_permissions(
        ...         connector_type=ConnectorType.GOOGLE_GMAIL,
        ...         required_scopes=["https://www.googleapis.com/auth/gmail.send"],
        ...         operation="send_email"
        ...     )

    Best Practices:
        - List specific scopes needed
        - Provide UI link to re-authorize with additional scopes
        - Log for analytics (track feature adoption vs scope requests)
    """
    logger.warning(
        "insufficient_oauth_permissions",
        connector_type=connector_type.value,
        required_scopes=required_scopes,
        operation=operation,
    )

    connector_name = connector_type.value.replace("_", " ").title()

    # Format scopes in user-friendly way
    scope_names = [scope.split("/")[-1] for scope in required_scopes]

    return {
        "success": False,
        "error": "insufficient_permissions",
        "message": APIMessages.insufficient_permissions(connector_name, scope_names, operation),
        "metadata": {
            FIELD_ERROR_TYPE: "InsufficientPermissionsError",
            "connector_type": connector_type.value,
            "required_scopes": required_scopes,
            "requires_reauth": True,
        },
    }


# ============================================================================
# Rate Limit Errors (429, 403 Rate Limit)
# ============================================================================


def handle_rate_limit_error(
    connector_type: ConnectorType,
    *,
    retry_after_seconds: int | None = None,
    error_detail: str | None = None,
) -> dict[str, Any]:
    """
    Handle API rate limit errors (429 Too Many Requests, 403 userRateLimitExceeded).

    Returns user-friendly error with retry advice.

    Args:
        connector_type: Type of connector
        retry_after_seconds: Retry-After header value (seconds to wait)
        error_detail: Optional detailed error message from API

    Returns:
        Error response dict with message and metadata

    Example:
        >>> try:
        ...     response = await gmail_api.list_messages()
        ... except httpx.HTTPStatusError as e:
        ...     if e.response.status_code == 429:
        ...         retry_after = int(e.response.headers.get("Retry-After", 60))
        ...         return handle_rate_limit_error(
        ...             connector_type=ConnectorType.GOOGLE_GMAIL,
        ...             retry_after_seconds=retry_after
        ...         )

    Best Practices:
        - Respect Retry-After header
        - Log for quota monitoring
        - Consider exponential backoff for retries
        - Alert if rate limits hit frequently (quota issue)
    """
    logger.warning(
        "api_rate_limit_exceeded",
        connector_type=connector_type.value,
        retry_after_seconds=retry_after_seconds,
        error_detail=error_detail,
    )

    connector_name = connector_type.value.replace("_", " ").title()

    return {
        "success": False,
        "error": "rate_limit_exceeded",
        "message": APIMessages.rate_limit_exceeded(connector_name, retry_after_seconds),
        "metadata": {
            FIELD_ERROR_TYPE: "RateLimitError",
            "connector_type": connector_type.value,
            "retry_after_seconds": retry_after_seconds,
            "retryable": True,
        },
    }


# ============================================================================
# Exponential Backoff Retry Decorator
# ============================================================================


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    min_wait_seconds: float = 1.0,
    max_wait_seconds: float = 10.0,
    *,
    retry_on: tuple[type[Exception], ...] = (httpx.HTTPStatusError,),
    operation_name: str = "api_call",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator for automatic retry with exponential backoff on transient failures.

    Retries on:
    - 5xx server errors (transient)
    - Network errors (timeouts, connection failures)
    - Custom exception types via retry_on parameter

    Does NOT retry on:
    - 4xx client errors (except 429 rate limit)
    - Authentication errors (401)
    - Permission errors (403)

    Args:
        max_attempts: Maximum retry attempts (default: 3)
        min_wait_seconds: Minimum wait between retries (default: 1s)
        max_wait_seconds: Maximum wait between retries (default: 10s)
        retry_on: Tuple of exception types to retry (default: httpx.HTTPStatusError)
        operation_name: Name for logging (default: "api_call")

    Returns:
        Decorated async function with retry logic

    Example:
        >>> @retry_with_exponential_backoff(
        ...     max_attempts=3,
        ...     retry_on=(httpx.HTTPStatusError, httpx.TimeoutException),
        ...     operation_name="gmail_list_messages"
        ... )
        ... async def list_messages(self):
        ...     response = await self.client.get("/gmail/v1/users/me/messages")
        ...     response.raise_for_status()
        ...     return response.json()

    Retry Schedule (exponential backoff):
        Attempt 1: Immediate
        Attempt 2: Wait 1-2s (exponential: 2^1)
        Attempt 3: Wait 2-4s (exponential: 2^2)
        Max: 10s

    Best Practices:
        - Use for all external API calls
        - Set appropriate max_attempts (3-5 for transient errors)
        - Log retry attempts for monitoring
        - Consider circuit breaker pattern for persistent failures
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = 0

            try:
                async for attempt_obj in AsyncRetrying(
                    retry=retry_if_exception_type(retry_on),
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential(
                        multiplier=1,
                        min=min_wait_seconds,
                        max=max_wait_seconds,
                    ),
                    reraise=True,
                ):
                    with attempt_obj:
                        attempt = attempt_obj.retry_state.attempt_number

                        if attempt > 1:
                            logger.warning(
                                f"{operation_name}_retry_attempt",
                                attempt=attempt,
                                max_attempts=max_attempts,
                            )

                        result = await func(*args, **kwargs)
                        return result

            except RetryError as e:
                # All retries exhausted
                original_exception = e.last_attempt.exception()
                logger.error(
                    f"{operation_name}_retry_exhausted",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(original_exception) if original_exception else "Unknown error",
                    error_type=(
                        type(original_exception).__name__ if original_exception else "Unknown"
                    ),
                )
                # Re-raise the original exception
                if original_exception is not None:
                    raise original_exception from e
                raise RuntimeError("Retry exhausted with no exception") from e

            # This should never be reached due to AsyncRetrying behavior
            # but is needed for MyPy to understand the control flow
            raise RuntimeError("AsyncRetrying did not return or raise")  # pragma: no cover

        return wrapper

    return decorator


# ============================================================================
# HTTP Error Classification
# ============================================================================


def classify_http_error(
    status_code: int,
    response_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify HTTP error and return metadata for proper handling.

    Args:
        status_code: HTTP status code
        response_body: Optional response body dict

    Returns:
        Dict with classification metadata:
        - error_category: "oauth", "permission", "rate_limit", "server", "client"
        - retryable: bool
        - requires_user_action: bool
        - suggested_action: str

    Example:
        >>> try:
        ...     response = await api_call()
        ... except httpx.HTTPStatusError as e:
        ...     classification = classify_http_error(
        ...         e.response.status_code,
        ...         e.response.json()
        ...     )
        ...     if classification["retryable"]:
        ...         # Retry logic
        ...     elif classification["requires_user_action"]:
        ...         # Notify user

    Use Cases:
        - Determine if error is retryable
        - Route to appropriate error handler
        - Generate user-facing error messages
        - Metrics/alerting categorization
    """
    error_code = response_body.get("error", {}).get("code") if response_body else None

    # OAuth errors (401)
    if status_code == 401:
        return {
            "error_category": "oauth",
            "retryable": False,
            "requires_user_action": True,
            "suggested_action": "reconnect_oauth",
            "http_status": status_code,
        }

    # Permission errors (403)
    if status_code == 403:
        # Distinguish between rate limit and permissions
        if error_code in ("userRateLimitExceeded", "rateLimitExceeded"):
            return {
                "error_category": "rate_limit",
                "retryable": True,
                "requires_user_action": False,
                "suggested_action": "wait_and_retry",
                "http_status": status_code,
            }
        else:
            return {
                "error_category": "permission",
                "retryable": False,
                "requires_user_action": True,
                "suggested_action": "request_additional_scopes",
                "http_status": status_code,
            }

    # Rate limit errors (429)
    if status_code == 429:
        return {
            "error_category": "rate_limit",
            "retryable": True,
            "requires_user_action": False,
            "suggested_action": "wait_and_retry",
            "http_status": status_code,
        }

    # Server errors (5xx) - transient
    if 500 <= status_code < 600:
        return {
            "error_category": "server",
            "retryable": True,
            "requires_user_action": False,
            "suggested_action": "retry_with_backoff",
            "http_status": status_code,
        }

    # Client errors (4xx) - non-retryable
    if 400 <= status_code < 500:
        return {
            "error_category": "client",
            "retryable": False,
            "requires_user_action": True,
            "suggested_action": "fix_request_parameters",
            "http_status": status_code,
        }

    # Unknown error
    return {
        "error_category": "unknown",
        "retryable": False,
        "requires_user_action": True,
        "suggested_action": "contact_support",
        "http_status": status_code,
    }


__all__ = [
    # OAuth Callback (Phase 3.2.10)
    "OAuthCallbackErrorCode",
    "classify_oauth_callback_error",
    "handle_oauth_callback_error_redirect",
    # OAuth & API Errors
    "classify_http_error",
    "handle_insufficient_permissions",
    "handle_oauth_error",
    "handle_rate_limit_error",
    "retry_with_exponential_backoff",
]
