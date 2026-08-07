"""Domain-specific exception families of the central taxonomy.

Extracted from ``src.core.exceptions`` (ADR-124, file-size ratchet): these
families are bounded-context specific (memory store, interests, voice STT,
WebSocket, usage limits) and only depend on ``BaseAPIException``. They remain part of the
central taxonomy — ``src.core.exceptions`` re-exports every name below, and
consumers keep importing from there (façade, no import change anywhere).

ADR Reference: ADR-002 (Unified Error Handling), ADR-124 (rule #18 phase 2).
"""

from typing import Any, NoReturn

from fastapi import status

from src.core._exceptions_base import BaseAPIException

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
# Interest Store Errors
# ============================================================================


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


# ============================================================================
# Usage Limit Errors
# ============================================================================


class UsageLimitExceededError(BaseAPIException):
    """Raised when a usage limit blocks the request (per user, or instance-wide).

    Two shapes on purpose:
    - without ``error_code``, the historical plain-string detail, so every
      existing caller and client keeps working unchanged;
    - with one, a structured detail (same doctrine as the 409 active-run
      contract) plus ``Retry-After``, because an instance pause is not the
      visitor's quota and must be told apart.
    """

    def __init__(
        self,
        limit_name: str | None = None,
        reason: str | None = None,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.limit_name = limit_name
        self.reason = reason
        self.error_code = error_code

        detail: str | dict[str, Any]
        if error_code is None:
            detail = reason or "Usage limit exceeded"
        else:
            detail = {
                "error": reason or "Usage limit exceeded",
                "error_code": error_code,
                "limit": limit_name,
            }

        headers = (
            {"Retry-After": str(retry_after_seconds)} if retry_after_seconds is not None else None
        )

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            log_event="usage_limit_exceeded",
            headers=headers,
            limit_name=limit_name or "unknown",
            **kwargs,
        )


def raise_usage_limit_exceeded(
    limit_name: str | None = None,
    reason: str | None = None,
    error_code: str | None = None,
    retry_after_seconds: int | None = None,
) -> NoReturn:
    """
    Raise when a usage limit blocks the request.

    Args:
        limit_name: Which limit was exceeded (e.g., 'cycle_tokens', 'manual_block').
        reason: Technical reason for the block (logs and admin API; what the
            visitor reads is localized by the frontend from the error code).
        error_code: Stable code the client localizes on. Supplying it switches
            the response to the structured detail shape.
        retry_after_seconds: Seconds before retrying makes sense.

    Raises:
        UsageLimitExceededError: 429 Too Many Requests
    """
    raise UsageLimitExceededError(
        limit_name=limit_name,
        reason=reason,
        error_code=error_code,
        retry_after_seconds=retry_after_seconds,
    )
