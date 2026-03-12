"""
Tool rate limiting for LangGraph agents.

Provides decorators and utilities for rate limiting tool invocations to prevent
abuse and protect external APIs (Google Contacts, Gmail, Calendar, etc.).

Architecture (LangGraph v1.0 Best Practices):
    - Per-user rate limits (isolated by user_id)
    - Per-tool rate limits (different limits for different operations)
    - Sliding window algorithm (more accurate than fixed window)
    - Graceful degradation (returns error instead of exception)
    - Metrics integration (track rate limit hits)
    - Configuration via Settings (environment variables)

Usage:
    from src.core.config import settings
    from src.domains.agents.constants import RATE_LIMIT_SCOPE_USER

    @tool
    @rate_limit(
        max_calls=settings.rate_limit_contacts_search_calls,
        window_seconds=settings.rate_limit_contacts_search_window,
        scope=RATE_LIMIT_SCOPE_USER,
    )
    async def search_contacts_tool(query: str, runtime: ToolRuntime) -> str:
        # Tool implementation
        pass
"""

import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from typing import Any

import structlog
from langchain.tools import ToolRuntime

from src.core.field_names import FIELD_TOOL_NAME, FIELD_USER_ID
from src.domains.agents.constants import (
    RATE_LIMIT_DEFAULT_READ_CALLS,
    RATE_LIMIT_DEFAULT_READ_WINDOW_SECONDS,
    RATE_LIMIT_SCOPE_USER,
)
from src.infrastructure.observability.metrics_agents import agent_tool_rate_limit_hits

logger = structlog.get_logger(__name__)


# In-memory rate limit tracking (per-tool, per-user)
# Structure: {(tool_name, user_id): [(timestamp1, timestamp2, ...)]}
_rate_limit_tracker: dict[tuple[str, str], list[float]] = defaultdict(list)


def rate_limit(
    max_calls: (
        int | Callable[[], int]
    ) = RATE_LIMIT_DEFAULT_READ_CALLS,  # From constants: 20 calls, or lambda for dynamic
    window_seconds: (
        int | Callable[[], int]
    ) = RATE_LIMIT_DEFAULT_READ_WINDOW_SECONDS,  # From constants: 60 seconds, or lambda
    scope: str = RATE_LIMIT_SCOPE_USER,  # From constants: "user"
    error_message: str | None = None,
) -> Callable:
    """
    Decorator for rate limiting tool invocations.

    Implements sliding window rate limiting with per-user isolation.
    When limit is exceeded, returns a JSON error message instead of executing the tool.

    Args:
        max_calls: Maximum number of calls allowed within the time window.
                  Can be an int or a Callable[[], int] (lambda) for dynamic settings.
                  Default: RATE_LIMIT_DEFAULT_READ_CALLS (20 calls).
                  Example: lambda: get_settings().rate_limit_contacts_search_calls
        window_seconds: Time window in seconds for rate limiting.
                       Can be an int or a Callable[[], int] (lambda) for dynamic settings.
                       Default: RATE_LIMIT_DEFAULT_READ_WINDOW_SECONDS (60 seconds).
                       Example: lambda: get_settings().rate_limit_contacts_search_window
        scope: Rate limit scope - "user" (per-user limits) or "global" (shared across all users).
               Default: RATE_LIMIT_SCOPE_USER ("user", recommended for multi-tenant security).
        error_message: Custom error message when rate limit exceeded. If None, uses default.

    Returns:
        Decorator function.

    Usage:
        >>> # Example 1: Static limits (simple)
        >>> @tool
        >>> @rate_limit(max_calls=20, window_seconds=60, scope="user")
        >>> async def search_contacts_tool(query: str, runtime: ToolRuntime) -> str:
        ...     # Tool implementation
        ...     pass
        >>>
        >>> # Example 2: Dynamic limits from settings (recommended)
        >>> @tool
        >>> @rate_limit(
        ...     max_calls=lambda: get_settings().rate_limit_contacts_search_calls,
        ...     window_seconds=lambda: get_settings().rate_limit_contacts_search_window,
        ...     scope="user",
        ... )
        >>> async def search_contacts_tool(query: str, runtime: ToolRuntime) -> str:
        ...     # Tool implementation - limits read from settings at runtime
        ...     pass
        >>>
        >>> # Example 3: Write operations (lower limit)
        >>> @tool
        >>> @rate_limit(max_calls=5, window_seconds=60, scope="user")
        >>> async def send_email_tool(to: str, subject: str, body: str, runtime: ToolRuntime) -> str:
        ...     # Tool implementation
        ...     pass

    Best Practices:
        - Read operations: 10-20 calls/min (search, list, get)
        - Write operations: 5-10 calls/min (create, update, delete)
        - Expensive operations: 1-5 calls/5min (export, bulk operations)
        - Use scope="user" for security (prevents one user from blocking others)

    Error Response:
        When rate limit is exceeded, returns JSON:
        {
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please wait before trying again.",
            "retry_after_seconds": 45,
            "limit": "10 calls per 60 seconds"
        }

    Metrics:
        Tracks rate limit hits via Prometheus metric:
        - agent_tool_rate_limit_hits{tool_name, user_id_hash, scope}

    Note:
        - Rate limits are stored in-memory (reset on server restart)
        - For production: Consider using Redis for distributed rate limiting
        - Sliding window ensures smooth distribution of calls
    """

    def decorator(func: Callable) -> Callable:
        tool_name = func.__name__

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check if rate limiting is globally enabled
            from src.core.config import get_settings

            settings = get_settings()
            if not settings.rate_limit_enabled:
                # Rate limiting disabled - clear tracker and execute tool directly
                # Clear tracker to avoid stale data when re-enabling
                if _rate_limit_tracker:
                    _rate_limit_tracker.clear()
                    logger.debug("rate_limiting_disabled_cleared_tracker")
                return await func(*args, **kwargs)

            # Resolve max_calls and window_seconds if they are callables (lambda pattern)
            # This allows dynamic reading from settings at runtime
            resolved_max_calls = max_calls() if callable(max_calls) else max_calls
            resolved_window_seconds = (
                window_seconds() if callable(window_seconds) else window_seconds
            )

            # Extract runtime parameter (should be in kwargs with ToolRuntime pattern)
            runtime: ToolRuntime | None = kwargs.get("runtime")

            if not runtime:
                # If runtime not available, skip rate limiting (fail open for compatibility)
                logger.warning(
                    "rate_limit_no_runtime",
                    tool_name=tool_name,
                    message="ToolRuntime not found, skipping rate limit check",
                )
                return await func(*args, **kwargs)

            # Extract user_id from runtime.config
            user_id = (runtime.config.get("configurable") or {}).get(FIELD_USER_ID)

            if not user_id:
                # If user_id not available, skip rate limiting (fail open)
                logger.warning(
                    "rate_limit_no_user_id",
                    tool_name=tool_name,
                    message="user_id not found in config, skipping rate limit check",
                )
                return await func(*args, **kwargs)

            # Determine rate limit key based on scope
            if scope == "user":
                limit_key = (tool_name, str(user_id))
            else:  # global scope
                limit_key = (tool_name, "__global__")

            # Get current timestamp
            now = time.time()

            # Get call history for this key
            call_history = _rate_limit_tracker[limit_key]

            # Remove calls outside the time window (sliding window)
            window_start = now - resolved_window_seconds
            call_history[:] = [ts for ts in call_history if ts > window_start]

            # Check if rate limit exceeded
            if len(call_history) >= resolved_max_calls:
                # Calculate retry_after (time until oldest call expires)
                oldest_call = call_history[0]
                retry_after_seconds = int(resolved_window_seconds - (now - oldest_call) + 1)

                # Track rate limit hit in metrics
                user_id_hash = str(hash(str(user_id)))[:8]
                agent_tool_rate_limit_hits.labels(
                    tool_name=tool_name,
                    user_id_hash=user_id_hash,
                    scope=scope,
                ).inc()

                # Log rate limit hit
                logger.warning(
                    "rate_limit_exceeded",
                    tool_name=tool_name,
                    user_id_preview=str(user_id)[:8],
                    max_calls=resolved_max_calls,
                    window_seconds=resolved_window_seconds,
                    retry_after_seconds=retry_after_seconds,
                    scope=scope,
                )

                # Return error message (graceful degradation)
                default_message = (
                    f"Limite de requêtes dépassée pour {tool_name}. "
                    f"Veuillez patienter {retry_after_seconds} secondes avant de réessayer."
                )

                import json

                return json.dumps(
                    {
                        "error": "rate_limit_exceeded",
                        "message": error_message or default_message,
                        "retry_after_seconds": retry_after_seconds,
                        "limit": f"{resolved_max_calls} calls per {resolved_window_seconds} seconds",
                        FIELD_TOOL_NAME: tool_name,
                    },
                    ensure_ascii=False,
                )

            # Rate limit not exceeded - record this call and execute
            call_history.append(now)

            # Execute the tool
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_rate_limit_status(tool_name: str, user_id: str) -> dict[str, Any]:
    """
    Get current rate limit status for a tool and user.

    Useful for debugging and monitoring.

    Args:
        tool_name: Name of the tool to check.
        user_id: User ID to check.

    Returns:
        Dictionary with rate limit status:
        {
            "calls_in_window": 7,
            "oldest_call_age_seconds": 45,
            "call_timestamps": [1234567890.0, 1234567900.0, ...]
        }

    Example:
        >>> status = get_rate_limit_status("search_contacts_tool", user_id)
        >>> print(f"User has made {status['calls_in_window']} calls")
    """
    limit_key = (tool_name, str(user_id))
    call_history = _rate_limit_tracker.get(limit_key, [])

    now = time.time()
    oldest_call_age = (now - call_history[0]) if call_history else 0

    return {
        "calls_in_window": len(call_history),
        "oldest_call_age_seconds": int(oldest_call_age),
        "call_timestamps": call_history,
    }


def reset_rate_limits(tool_name: str | None = None, user_id: str | None = None) -> None:
    """
    Reset rate limits for debugging or admin operations.

    Args:
        tool_name: Optional tool name to reset (if None, resets all tools).
        user_id: Optional user ID to reset (if None, resets all users).

    Examples:
        >>> # Reset all rate limits
        >>> reset_rate_limits()
        >>>
        >>> # Reset rate limits for specific tool
        >>> reset_rate_limits(tool_name="search_contacts_tool")
        >>>
        >>> # Reset rate limits for specific user
        >>> reset_rate_limits(user_id="123e4567-e89b-12d3-a456-426614174000")
        >>>
        >>> # Reset rate limits for specific tool + user
        >>> reset_rate_limits(tool_name="search_contacts_tool", user_id="123...")

    Warning:
        This function is intended for debugging and admin operations only.
        Do not expose this function to end users.
    """
    if tool_name is None and user_id is None:
        # Reset all rate limits
        _rate_limit_tracker.clear()
        logger.info("rate_limits_reset_all")

    elif tool_name and user_id:
        # Reset specific tool + user
        limit_key = (tool_name, str(user_id))
        if limit_key in _rate_limit_tracker:
            del _rate_limit_tracker[limit_key]
            logger.info("rate_limit_reset", tool_name=tool_name, user_id_preview=str(user_id)[:8])

    elif tool_name:
        # Reset all users for specific tool
        keys_to_delete = [key for key in _rate_limit_tracker.keys() if key[0] == tool_name]
        for key in keys_to_delete:
            del _rate_limit_tracker[key]
        logger.info("rate_limits_reset_tool", tool_name=tool_name, count=len(keys_to_delete))

    elif user_id:
        # Reset all tools for specific user
        user_id_str = str(user_id)
        keys_to_delete = [key for key in _rate_limit_tracker.keys() if key[1] == user_id_str]
        for key in keys_to_delete:
            del _rate_limit_tracker[key]
        logger.info(
            "rate_limits_reset_user", user_id_preview=user_id_str[:8], count=len(keys_to_delete)
        )


__all__ = [
    "get_rate_limit_status",
    "rate_limit",
    "reset_rate_limits",
]
