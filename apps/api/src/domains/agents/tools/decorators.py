"""
Tool Decorator Presets - Eliminate decorator boilerplate.

This module provides high-level decorator presets that combine multiple
decorators (metrics, rate limiting, context saving) based on tool category.

Design Philosophy:
- DRY: One decorator instead of 3-4 stacked decorators
- Category-based: Different presets for read/write/expensive operations
- Convention over Configuration: Sensible defaults, override when needed
- Future-proof: Easy to add new decorators without touching every tool

Architecture:
- connector_tool(): Main decorator combining @tool + @track_tool_metrics + @rate_limit + @auto_save_context
- Category-based rate limits: "read", "write", "expensive"
- Automatic agent_name inference from tool_name pattern

Benefits:
- Reduces from 4 decorator lines to 1 (75% reduction)
- Eliminates 14 lines × 4 tools = 56 lines of boilerplate
- Makes adding new tools trivial (copy-paste, change name/category)
- Ensures consistency (all tools use same decorators)

Usage Example:
    from src.domains.agents.tools.decorators import connector_tool

    # Old way (4 decorators):
    @tool
    @track_tool_metrics(tool_name="search_contacts", agent_name="contacts_agent", ...)
    @rate_limit(max_calls=20, window_seconds=60, scope="user")
    @auto_save_context("contacts")
    async def search_contacts_tool(...):
        pass

    # New way (1 decorator):
    @connector_tool(
        name="search_contacts",
        agent_name="contacts_agent",
        context_domain="contacts",
        category="read",
    )
    async def search_contacts_tool(...):
        pass
"""

from collections.abc import Callable
from typing import Literal, TypeVar, cast

from langchain_core.tools import tool

from src.core.config import get_settings
from src.domains.agents.context import auto_save_context
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

T = TypeVar("T")

# Rate limit category mappings (uses default settings from connectors.py)
RATE_LIMIT_CATEGORIES = {
    "read": {  # Read operations (search, list, get) - 20 calls/min
        "max_calls": lambda: get_settings().rate_limit_default_read_calls,
        "window_seconds": lambda: get_settings().rate_limit_default_read_window,
    },
    "write": {  # Write operations (create, update, delete, send) - 5 calls/min
        "max_calls": lambda: get_settings().rate_limit_default_write_calls,
        "window_seconds": lambda: get_settings().rate_limit_default_write_window,
    },
    "expensive": {  # Expensive operations (export, bulk) - 2 calls/5min
        "max_calls": lambda: get_settings().rate_limit_default_expensive_calls,
        "window_seconds": lambda: get_settings().rate_limit_default_expensive_window,
    },
}


def connector_tool(
    *,
    name: str,
    agent_name: str,
    context_domain: str | None = None,
    category: Literal["read", "write", "expensive"] = "read",
    rate_limit_max_calls: int | Callable[[], int] | None = None,
    rate_limit_window_seconds: int | Callable[[], int] | None = None,
    rate_limit_scope: str = "user",
    description: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    All-in-one decorator preset for connector tools.

    Combines:
    - @tool: LangChain tool registration
    - @track_tool_metrics: Automatic metrics tracking (duration, success/failure)
    - @rate_limit: Rate limiting based on category (read/write/expensive)
    - @auto_save_context: Automatic context saving to Store (optional)

    Args:
        name: Tool name for metrics/logging (e.g., "search_contacts")
        agent_name: Agent owning the tool (e.g., "contacts_agent")
        context_domain: Domain for context saving (e.g., "contacts"), or None to skip
        category: Rate limit category - "read" (20/min), "write" (5/min), or "expensive" (2/5min)
        rate_limit_max_calls: Override category default for max_calls
        rate_limit_window_seconds: Override category default for window_seconds
        rate_limit_scope: Rate limit scope - "user" (per-user) or "global" (shared)
        description: Tool description for LangChain (optional, uses docstring if None)

    Returns:
        Decorated function with all decorators applied

    Example:
        >>> # Read operation with context saving
        >>> @connector_tool(
        ...     name="search_contacts",
        ...     agent_name="contacts_agent",
        ...     context_domain="contacts",
        ...     category="read",
        ... )
        >>> async def search_contacts_tool(
        ...     query: str,
        ...     runtime: Annotated[ToolRuntime, InjectedToolArg],
        ... ) -> str:
        ...     '''Recherche des contacts Google par nom, email ou téléphone.'''
        ...     # Implementation
        ...     pass

        >>> # Write operation without context saving
        >>> @connector_tool(
        ...     name="send_email",
        ...     agent_name="emails_agent",
        ...     category="write",
        ... )
        >>> async def send_email_tool(
        ...     to: str,
        ...     subject: str,
        ...     body: str,
        ...     runtime: Annotated[ToolRuntime, InjectedToolArg],
        ... ) -> str:
        ...     '''Envoie un email via Gmail.'''
        ...     # Implementation
        ...     pass

        >>> # Expensive operation with custom rate limits
        >>> @connector_tool(
        ...     name="export_contacts",
        ...     agent_name="contacts_agent",
        ...     category="expensive",
        ...     rate_limit_max_calls=1,
        ...     rate_limit_window_seconds=3600,  # 1 call per hour
        ... )
        >>> async def export_contacts_tool(...):
        ...     # Implementation
        ...     pass

    Decorator Order (innermost to outermost):
        1. Original function
        2. @track_tool_metrics (tracks duration/success - must be closest to func)
        3. @rate_limit (checks rate limit before execution)
        4. @auto_save_context (saves results after successful execution)
        5. @tool (LangChain registration - must be outermost)

    Notes:
        - Category-based rate limits follow best practices:
          - "read": 20 calls/min (search, list, get)
          - "write": 5 calls/min (create, update, delete, send)
          - "expensive": 2 calls/5min (export, bulk)
        - context_domain=None skips context saving (for write operations)
        - All decorators are optional - customize via parameters
        - Description comes from docstring if not provided
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Step 1: Apply @track_tool_metrics (innermost - closest to func)
        # This must be first to accurately track execution time
        decorated = track_tool_metrics(
            tool_name=name,
            agent_name=agent_name,
            duration_metric=agent_tool_duration_seconds,
            counter_metric=agent_tool_invocations,
            log_execution=True,
            log_errors=True,
        )(func)

        # Step 2: Apply @rate_limit
        # Determine rate limits from category or overrides
        if rate_limit_max_calls is not None and rate_limit_window_seconds is not None:
            # Use custom overrides
            max_calls = rate_limit_max_calls
            window_seconds = rate_limit_window_seconds
        else:
            # Use category defaults
            rate_limits = RATE_LIMIT_CATEGORIES.get(category, RATE_LIMIT_CATEGORIES["read"])
            max_calls = rate_limits["max_calls"]
            window_seconds = rate_limits["window_seconds"]

        decorated = rate_limit(
            max_calls=max_calls,
            window_seconds=window_seconds,
            scope=rate_limit_scope,
        )(decorated)

        # Step 3: Apply @auto_save_context (if context_domain provided)
        if context_domain is not None:
            decorated = auto_save_context(context_domain)(decorated)

        # Step 4: Apply @tool (outermost - LangChain registration)
        # Description comes from docstring if not provided
        if description is not None:
            # Use provided description
            decorated = tool(description=description)(decorated)
        else:
            # Use docstring
            decorated = tool(decorated)

        return cast(Callable[..., T], decorated)

    return decorator


def read_tool(
    *,
    name: str,
    agent_name: str,
    context_domain: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Preset decorator for read operations (search, list, get).

    Shorthand for @connector_tool with category="read" (20 calls/min).

    Args:
        name: Tool name
        agent_name: Agent name
        context_domain: Domain for context saving (optional)

    Returns:
        Decorated function

    Example:
        >>> @read_tool(
        ...     name="search_contacts",
        ...     agent_name="contacts_agent",
        ...     context_domain="contacts",
        ... )
        >>> async def search_contacts_tool(...):
        ...     pass
    """
    return connector_tool(
        name=name,
        agent_name=agent_name,
        context_domain=context_domain,
        category="read",
    )


def write_tool(
    *,
    name: str,
    agent_name: str,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Preset decorator for write operations (create, update, delete, send).

    Shorthand for @connector_tool with category="write" (5 calls/min).
    Note: Write operations typically don't save context, so context_domain is excluded.

    Args:
        name: Tool name
        agent_name: Agent name

    Returns:
        Decorated function

    Example:
        >>> @write_tool(
        ...     name="send_email",
        ...     agent_name="emails_agent",
        ... )
        >>> async def send_email_tool(...):
        ...     pass
    """
    return connector_tool(
        name=name,
        agent_name=agent_name,
        context_domain=None,  # Write operations don't save context
        category="write",
    )


def expensive_tool(
    *,
    name: str,
    agent_name: str,
    max_calls: int = 2,
    window_seconds: int = 300,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Preset decorator for expensive operations (export, bulk).

    Shorthand for @connector_tool with category="expensive" (2 calls/5min).

    Args:
        name: Tool name
        agent_name: Agent name
        max_calls: Maximum calls (default: 2)
        window_seconds: Time window in seconds (default: 300 = 5 minutes)

    Returns:
        Decorated function

    Example:
        >>> @expensive_tool(
        ...     name="export_contacts",
        ...     agent_name="contacts_agent",
        ...     max_calls=1,
        ...     window_seconds=3600,  # 1 call per hour
        ... )
        >>> async def export_contacts_tool(...):
        ...     pass
    """
    return connector_tool(
        name=name,
        agent_name=agent_name,
        context_domain=None,  # Expensive operations don't save context
        category="expensive",
        rate_limit_max_calls=max_calls,
        rate_limit_window_seconds=window_seconds,
    )


def with_user_preferences(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that automatically injects user preferences into tool kwargs.

    This decorator eliminates the duplicate try-except pattern for user preferences
    fetching that appears in 25+ tool methods. It automatically:
    1. Fetches user timezone, language, and locale from database
    2. Injects them into kwargs as 'user_timezone' and 'locale'
    3. Falls back to defaults ("UTC", "fr") on any error

    The decorated function receives:
        - user_timezone: str (from user.timezone or "UTC")
        - locale: str (from user.language or "fr")

    This centralizes the user preferences lookup pattern and makes it
    explicit via decorator rather than hidden in each tool's implementation.

    Args:
        func: Async tool function to decorate

    Returns:
        Decorated function with user_timezone and locale injected

    Example:
        >>> from langchain.tools import ToolRuntime
        >>> from langchain_core.tools import InjectedToolArg
        >>> from typing import Annotated
        >>>
        >>> @connector_tool(name="search_events", agent_name="calendar_agent", category="read")
        >>> @with_user_preferences  # Injects user_timezone and locale
        >>> async def search_events_tool(
        ...     query: str,
        ...     runtime: Annotated[ToolRuntime, InjectedToolArg],
        ...     user_timezone: str = "UTC",  # Injected by decorator
        ...     locale: str = "fr",          # Injected by decorator
        ... ) -> UnifiedToolOutput:
        ...     # user_timezone and locale are already available
        ...     # No need for try-except get_user_preferences() boilerplate
        ...     events = await client.search_events(query)
        ...     return self.build_events_output(events, user_timezone=user_timezone, locale=locale)

    Note:
        - This decorator should be applied AFTER @connector_tool (closer to the function)
        - It's fail-safe: any error in preferences fetch falls back to defaults
        - The injected values can be overridden by explicit kwargs if needed
    """
    from functools import wraps

    from src.core.constants import DEFAULT_LANGUAGE

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract runtime from kwargs (injected by LangChain)
        runtime = kwargs.get("runtime")

        # Default values
        user_timezone = "UTC"
        locale = DEFAULT_LANGUAGE

        if runtime:
            try:
                # Import here to avoid circular dependency
                from src.domains.agents.tools.runtime_helpers import get_user_preferences

                # Fetch user preferences from database
                fetched_tz, _, fetched_locale = await get_user_preferences(runtime)
                user_timezone = fetched_tz
                locale = fetched_locale
            except Exception:
                # Silent fallback to defaults
                # Logging is already done in get_user_preferences()
                pass

        # Inject into kwargs (unless already provided)
        kwargs.setdefault("user_timezone", user_timezone)
        kwargs.setdefault("locale", locale)

        # Call original function with injected preferences
        return await func(*args, **kwargs)

    return cast(Callable[..., T], wrapper)
