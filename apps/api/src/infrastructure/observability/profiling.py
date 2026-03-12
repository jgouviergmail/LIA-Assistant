"""
Performance profiling utilities.

Provides decorators and context managers for profiling code performance.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

import asyncio
import functools
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def profile_performance(
    func_name: str | None = None,
    log_threshold_ms: float = 100.0,
    log_level: str = "INFO",
) -> Callable:
    """
    Profile function performance.

    Args:
        func_name: Custom function name for logging (default: actual function name)
        log_threshold_ms: Only log if execution time > threshold (default: 100ms)
        log_level: Log level for performance logs (default: INFO)

    Usage:
        @profile_performance()
        def my_function():
            ...

        @profile_performance(log_threshold_ms=50.0)
        async def my_async_function():
            ...
    """

    def decorator(func: Callable) -> Callable:
        name = func_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if duration_ms >= log_threshold_ms:
                        log_func = getattr(logger, log_level.lower())
                        log_func(
                            "profile_function",
                            function=name,
                            duration_ms=round(duration_ms, 2),
                        )

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if duration_ms >= log_threshold_ms:
                        log_func = getattr(logger, log_level.lower())
                        log_func(
                            "profile_function",
                            function=name,
                            duration_ms=round(duration_ms, 2),
                        )

            return sync_wrapper

    return decorator


@contextmanager
def profile_block(block_name: str, log_threshold_ms: float = 100.0) -> Generator[None, None, None]:
    """
    Profile code block performance.

    Usage:
        with profile_block("expensive_operation"):
            # ... code to profile
            result = expensive_function()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        if duration_ms >= log_threshold_ms:
            logger.info(
                "profile_block",
                block_name=block_name,
                duration_ms=round(duration_ms, 2),
            )
