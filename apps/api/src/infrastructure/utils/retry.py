"""
Retry utilities with exponential backoff.

This module provides a reusable retry decorator for API clients and other
components that need to handle transient failures gracefully.

Usage:
    from src.infrastructure.utils.retry import retry_with_backoff

    @retry_with_backoff(
        max_retries=3,
        backoff_factor=2.0,
        retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError),
    )
    async def make_api_call():
        ...

Design:
    - Exponential backoff: wait_time = backoff_factor ** attempt
    - Configurable max retries and backoff factor
    - Structured logging for observability
    - Type-safe with full async support
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    operation_name: str | None = None,
    log_retries: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Base for exponential backoff calculation (default: 2.0)
                       Wait time = backoff_factor ** attempt
        retryable_exceptions: Tuple of exception types to retry on
        operation_name: Name for logging (defaults to function name)
        log_retries: Whether to log retry attempts (default: True)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(
            max_retries=3,
            retryable_exceptions=(httpx.TimeoutException,)
        )
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                return await client.get(url)

    Raises:
        MaxRetriesExceededError: When all retry attempts are exhausted
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            op_name = operation_name or func.__name__
            last_exception: Exception | None = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)  # type: ignore[misc, no-any-return]
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor**attempt
                        if log_retries:
                            logger.warning(
                                "retry_attempt",
                                operation=op_name,
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                wait_seconds=wait_time,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                        await asyncio.sleep(wait_time)
                    else:
                        # Last attempt failed
                        logger.error(
                            "max_retries_exceeded",
                            operation=op_name,
                            max_retries=max_retries,
                            last_error=str(e),
                            error_type=type(e).__name__,
                        )

            raise MaxRetriesExceededError(
                operation=op_name,
                max_retries=max_retries,
                last_error=last_exception,
            )

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            op_name = operation_name or func.__name__
            last_exception: Exception | None = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor**attempt
                        if log_retries:
                            logger.warning(
                                "retry_attempt",
                                operation=op_name,
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                wait_seconds=wait_time,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                        import time

                        time.sleep(wait_time)
                    else:
                        logger.error(
                            "max_retries_exceeded",
                            operation=op_name,
                            max_retries=max_retries,
                            last_error=str(e),
                            error_type=type(e).__name__,
                        )

            raise MaxRetriesExceededError(
                operation=op_name,
                max_retries=max_retries,
                last_error=last_exception,
            )

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper

    return decorator
