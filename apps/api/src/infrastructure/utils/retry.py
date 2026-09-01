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
import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


async def retry_async(
    factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    operation_name: str = "async_call",
    log_retries: bool = True,
) -> T:
    """Run ``factory()`` until it succeeds, with exponential backoff.

    The functional half of this module's retry policy. It takes a FACTORY, not
    an awaitable, and that is the whole reason it exists: a coroutine can be
    awaited exactly once, so a caller holding ``client.aembed_query(...)``
    cannot retry it — the second await raises instead of re-calling. Every
    attempt must build a fresh awaitable, which only the caller can do.

    :func:`retry_with_backoff` delegates here so the backoff, the logging and
    the exhaustion error have ONE implementation rather than two that drift.

    Args:
        factory: Builds a fresh awaitable for each attempt.
        max_retries: Total attempts, including the first (1 = no retry).
        backoff_factor: Wait is ``backoff_factor ** attempt`` seconds.
        retryable_exceptions: Only these are retried; anything else propagates
            unchanged, so a caller's typed error keeps its identity.
        operation_name: Name used in the structured logs.
        log_retries: Whether to log each retried attempt.

    Returns:
        Whatever the first successful attempt returned.

    Raises:
        MaxRetriesExceededError: Every attempt failed with a retryable error;
            ``last_error`` carries the final cause.
        Exception: Any non-retryable exception, re-raised untouched.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return await factory()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = backoff_factor**attempt
                if log_retries:
                    logger.warning(
                        "retry_attempt",
                        operation=operation_name,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    "max_retries_exceeded",
                    operation=operation_name,
                    max_retries=max_retries,
                    last_error=str(e),
                    error_type=type(e).__name__,
                )

    # `from last_exception`: the cause chain is what a CALLER classifies on.
    # `MaxRetriesExceededError` keeps the last error as an attribute only, and
    # this raise sits outside the `except`, so without this the chain ends here
    # — and a caller with its own retry (the system indexer walks `__cause__`
    # for the provider status code) sees a bare wrapper and calls the failure
    # permanent. Exhausting an inner retry must not erase WHY it failed.
    raise MaxRetriesExceededError(
        operation=operation_name,
        max_retries=max_retries,
        last_error=last_exception,
    ) from last_exception


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
            # Delegates to the functional core: one backoff policy, one place.
            return await retry_async(
                lambda: func(*args, **kwargs),  # type: ignore[arg-type, return-value]
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                retryable_exceptions=retryable_exceptions,
                operation_name=operation_name or func.__name__,
                log_retries=log_retries,
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
        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper

    return decorator
