r"""
Runtime helpers for LangChain tools and nodes.

Phase 3.2.8: Helper functions to eliminate code duplication across tools.
Phase 3.2.8.1: Extended to support nodes (State dict) in addition to tools (ToolRuntime).
Phase 3.2.9: Added comprehensive Store usage documentation to prevent async/sync interface errors.

Provides common utilities for:
- Runtime config validation (user_id, session_id, store)
- Error handling with consistent logging
- Session ID extraction from both ToolRuntime and State dict

CRITICAL - LangGraph Store Interface Usage
===========================================

LangGraph's AsyncPostgresStore has DUAL interfaces (sync + async) with DIFFERENT method names.
Using the wrong interface in async context causes InvalidStateError deadlocks.

╔══════════════════════════════════════════════════════════════════════════════╗
║                       STORE INTERFACE REFERENCE TABLE                         ║
╠═══════════════════════════╦══════════════════════╦═══════════════════════════╣
║ Context                   ║ Correct Interface    ║ Method Examples           ║
╠═══════════════════════════╬══════════════════════╬═══════════════════════════╣
║ ASYNC (tools, agents,     ║ Async methods        ║ await store.aput(...)     ║
║ endpoints)                ║ (prefix: 'a')        ║ await store.aget(...)     ║
║                           ║                      ║ await store.adelete(...)  ║
║                           ║                      ║ await store.asearch(...)  ║
╠═══════════════════════════╬══════════════════════╬═══════════════════════════╣
║ SYNC (tests, scripts,     ║ Sync methods         ║ store.put(...)            ║
║ CLI tools)                ║ (no prefix)          ║ store.get(...)            ║
║                           ║                      ║ store.delete(...)         ║
║                           ║                      ║ store.search(...)         ║
╠═══════════════════════════╬══════════════════════╬═══════════════════════════╣
║ ❌ NEVER USE              ║ Sync in async        ║ await store.put(...)      ║
║                           ║                      ║ await store.get(...)      ║
║                           ║                      ║ → InvalidStateError       ║
╚═══════════════════════════╩══════════════════════╩═══════════════════════════╝

Common Error Patterns to Avoid
-------------------------------

❌ BAD (InvalidStateError - Deadlock):
    async def my_tool(runtime: ToolRuntime):
        # WRONG: Using sync method in async context
        await runtime.store.put(
            namespace=("user_123", "session_456", "context", "domain"),
            key="my_key",
            value={"data": "value"}
        )

✅ GOOD (Correct async interface):
    async def my_tool(runtime: ToolRuntime):
        # CORRECT: Using async method in async context
        await runtime.store.aput(
            namespace=("user_123", "session_456", "context", "domain"),
            key="my_key",
            value={"data": "value"}
        )

Code Examples by Use Case
--------------------------

1. Store User Preferences (Tool):
    async def save_preference_tool(runtime: ToolRuntime, **kwargs):
        config = validate_runtime_config(runtime, "save_preference_tool")
        if isinstance(config, UnifiedToolOutput):
            return config  # Return error directly

        # ✅ CORRECT: aput in async context
        await runtime.store.aput(
            namespace=(config.user_id, config.session_id, "preferences", "app"),
            key="theme",
            value={"mode": "dark", "updated_at": datetime.now(UTC).isoformat()}
        )

2. Retrieve Conversation Context (Node):
    async def process_user_message(state: dict):
        from src.domains.agents.dependencies import get_dependencies, ToolDependencies
        deps: ToolDependencies = get_dependencies(state)
        store = deps.store

        session_id = extract_session_id_from_state(state, "process_user_message")
        user_id = state["user_id"]

        # ✅ CORRECT: aget in async context
        context = await store.aget(
            namespace=(user_id, session_id, "conversation", "memory"),
            key="summary"
        )

3. Delete Expired Cache (Agent):
    async def cleanup_expired_data(runtime: ToolRuntime):
        # ✅ CORRECT: adelete in async context
        await runtime.store.adelete(
            namespace=(str(user_id), session_id, "cache", "gmail"),
            key="messages_list"
        )

4. Search Historical Messages (Tool):
    async def search_history_tool(runtime: ToolRuntime, query: str):
        # ✅ CORRECT: asearch in async context
        results = await runtime.store.asearch(
            namespace_prefix=(user_id, session_id),
            filter={"type": "message"},
            limit=50
        )

Prevention Checklist
--------------------

Before committing code that uses runtime.store:

□ 1. Am I in an async context (async def)?
     → YES: Use aput/aget/adelete/asearch (prefix 'a')
     → NO: Use put/get/delete/search (no prefix)

□ 2. Did I add 'await' before store method call?
     → Async methods MUST have 'await'

□ 3. Did I test the code with real AsyncPostgresStore?
     → Mock stores may not catch interface errors

□ 4. Did I check pre-commit hooks passed?
     → Hook should detect synchronous store calls in async context

References
----------
- LangGraph Store Documentation: https://langchain-ai.github.io/langgraph/reference/store/
- AsyncPostgresStore Source: langgraph/store/postgres/aio.py
- Integration Guide: D:\\Developpement\\LIA\\docs\\evolutionsGoogle\\INTEGRATION_GUIDE.md (Section 5.7)
- Error #5 Documentation: INTEGRATION_GUIDE.md - Erreur Critique #5
"""

from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

from fastapi import HTTPException
from langchain.tools import ToolRuntime
from langgraph.store.base import BaseStore

from src.core.config import settings
from src.core.field_names import FIELD_ERROR_MESSAGE, FIELD_ERROR_TYPE, FIELD_USER_ID
from src.core.i18n_api_messages import APIMessages
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.tools.output import UnifiedToolOutput

logger = get_logger(__name__)


# =============================================================================
# USER ID PARSING
# =============================================================================


def parse_user_id(user_id: str | UUID) -> UUID:
    """
    Parse user_id to UUID, handling multiple input formats.

    Centralizes user_id parsing across all connector tools to ensure consistency.

    Supports:
    - UUID objects (returned as-is)
    - UUID strings with hyphens (e.g., '12345678-1234-1234-1234-123456789012')
    - UUID strings without hyphens (32 hex chars)
    - ULIDs as 26-char base32 strings (e.g., '01JA9XWN11N3J3BM0GZNB9FZKM')

    Args:
        user_id: User ID as string (UUID/ULID format) or UUID object

    Returns:
        UUID object

    Raises:
        ValueError: If user_id cannot be parsed

    Example:
        >>> from src.domains.agents.tools.runtime_helpers import parse_user_id
        >>> uuid_obj = parse_user_id("01JA9XWN11N3J3BM0GZNB9FZKM")  # ULID
        >>> uuid_obj = parse_user_id("12345678-1234-1234-1234-123456789012")  # UUID
    """
    # Handle UUID objects directly (injected by LangGraph)
    if isinstance(user_id, UUID):
        return user_id

    try:
        # Try direct UUID parsing (works for standard UUID with hyphens)
        return UUID(user_id)
    except ValueError:
        # If it fails, try adding hyphens for UUID format (32 hex chars without hyphens)
        if len(user_id) == 32 and "-" not in user_id:
            # Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            formatted = (
                f"{user_id[:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:]}"
            )
            return UUID(formatted)

        # If it's a ULID (26 chars, Crockford base32), convert to UUID
        if len(user_id) == 26 and "-" not in user_id:
            # ULID uses Crockford's base32 encoding
            # Map Crockford base32 to standard characters for decoding
            # Crockford: 0123456789ABCDEFGHJKMNPQRSTVWXYZ (excludes I, L, O, U)
            # We need to convert ULID to its 128-bit integer representation
            base32_chars = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
            try:
                # Decode ULID to 128-bit integer
                num = 0
                for char in user_id.upper():
                    num = num * 32 + base32_chars.index(char)
                # Convert to 16 bytes (128 bits)
                ulid_bytes = num.to_bytes(16, byteorder="big")
                return UUID(bytes=ulid_bytes)
            except (ValueError, OverflowError):
                pass

        # Last resort: raise error
        raise ValueError(f"Invalid user_id format: {user_id}") from None


# =============================================================================
# ERROR HANDLING
# =============================================================================


def handle_connector_api_error(
    error: Exception,
    operation: str,
    tool_name: str,
    params: dict[str, Any],
    user_id_str: str | None = None,
    metrics_counter: Any = None,
) -> "UnifiedToolOutput":
    """
    Unified error handling for all connector API operations.

    Handles both HTTPException (from connectors) and generic exceptions,
    tracking metrics and logging appropriately.

    This function centralizes error handling to eliminate duplication between
    different connector tools (Gmail, Contacts, Calendar, etc.).

    Args:
        error: The exception that occurred
        operation: Operation type (e.g., "search", "list", "get", "send")
        tool_name: Name of the tool for error context
        params: Tool parameters for error context
        user_id_str: User ID string for logging (optional)
        metrics_counter: Optional Prometheus counter for tracking errors.
                         Should have .labels(operation=..., status=...).inc() interface

    Returns:
        UnifiedToolOutput with error details

    Example:
        >>> from src.infrastructure.observability.metrics_agents import contacts_api_calls
        >>>
        >>> try:
        ...     result = await client.search_contacts(...)
        ... except Exception as e:
        ...     return handle_connector_api_error(
        ...         e, "search", "search_contacts_tool", {"query": query},
        ...         user_id_str=str(user_id),
        ...         metrics_counter=contacts_api_calls
        ...     )
    """
    from src.domains.agents.tools.output import UnifiedToolOutput

    # Track metric if counter provided (always, even if it fails)
    if metrics_counter is not None:
        try:
            metrics_counter.labels(
                operation=operation,
                status="error",
            ).inc()
        except Exception:
            pass  # Ignore errors in error tracking

    # Handle HTTPException (from connectors - API errors)
    if isinstance(error, HTTPException):
        logger.error(
            f"{operation}_connector_http_error",
            user_id=user_id_str,
            tool_name=tool_name,
            status_code=error.status_code,
            detail=error.detail,
        )
        return UnifiedToolOutput.failure(
            message=str(error.detail),
            error_code="http_error",
            metadata={"status_code": error.status_code},
        )

    # Handle generic exceptions (network, parsing, etc.)
    # Log with full context for debugging
    logger.error(
        f"{operation}_connector_unexpected_error",
        user_id=user_id_str,
        error_type=type(error).__name__,
        error_message=str(error),
        tool_name=tool_name,
        params=params,
        exc_info=True,
    )

    return handle_tool_exception(error, tool_name, params)


class ValidatedRuntimeConfig(NamedTuple):
    """Validated runtime configuration extracted from ToolRuntime."""

    user_id: str
    session_id: str
    store: BaseStore


def validate_runtime_config(
    runtime: ToolRuntime,
    tool_name: str,
) -> "UnifiedToolOutput | ValidatedRuntimeConfig":
    """
    Validate and extract runtime configuration from ToolRuntime.

    This helper eliminates the ~15 lines of duplication in each tool for:
    - Extracting user_id from runtime.config.configurable
    - Extracting session_id from runtime.config.configurable
    - Validating that runtime.store is available

    Args:
        runtime: ToolRuntime from LangChain tool execution
        tool_name: Name of the calling tool (for logging)

    Returns:
        Either:
        - UnifiedToolOutput (error) if validation fails
        - ValidatedRuntimeConfig if validation succeeds

    Example:
        >>> config = validate_runtime_config(runtime, "search_contacts_tool")
        >>> if isinstance(config, UnifiedToolOutput):
        ...     return config  # Error response (structured)
        >>> # Use validated config
        >>> user_id = config.user_id
        >>> session_id = config.session_id
        >>> store = config.store
    """
    from src.domains.agents.tools.output import UnifiedToolOutput

    # Extract user_id
    user_id = (runtime.config.get("configurable") or {}).get(FIELD_USER_ID)
    if not user_id:
        logger.error("missing_user_id", tool_name=tool_name)
        return UnifiedToolOutput.failure(
            message=f"{FIELD_USER_ID} missing in config.configurable",
            error_code="configuration_error",
        )

    # Extract session_id (thread_id in LangGraph v1.0 terminology)
    # LangGraph v1.0 uses "thread_id" in config.configurable for conversation threads
    # We normalize it to "session_id" internally for consistency with Store operations
    session_id = (runtime.config.get("configurable") or {}).get("thread_id")
    if not session_id:
        logger.error(
            f"{tool_name}_missing_thread_id",
            user_id=str(user_id),
        )
        return UnifiedToolOutput.failure(
            message="thread_id (session_id) missing in config.configurable. "
            "Ensure RunnableConfig has configurable={'thread_id': ...}",
            error_code="configuration_error",
        )

    # Validate store
    if not runtime.store:
        logger.error(
            f"{tool_name}_missing_store",
            user_id=str(user_id),
            session_id=session_id,
        )
        return UnifiedToolOutput.failure(
            message="Store not available in runtime",
            error_code="configuration_error",
        )

    # Return validated config
    return ValidatedRuntimeConfig(
        user_id=user_id,
        session_id=session_id,
        store=runtime.store,
    )


def handle_tool_exception(
    e: Exception,
    tool_name: str,
    context: dict[str, Any] | None = None,
) -> "UnifiedToolOutput":
    """
    Handle unexpected exceptions in tools with consistent error logging and response.

    This helper eliminates the ~10 lines of duplication in each tool for:
    - Logging the exception with context
    - Creating an error response

    Args:
        e: The exception that was raised
        tool_name: Name of the tool (for logging)
        context: Optional context dict for logging (e.g., {"query": "john"})

    Returns:
        UnifiedToolOutput with error details

    Example:
        >>> try:
        ...     result = await some_operation()
        ... except Exception as e:
        ...     return handle_tool_exception(e, "search_contacts_tool", {"query": query})
    """
    from src.domains.agents.tools.output import UnifiedToolOutput

    logger.error(
        f"{tool_name}_unexpected_error",
        error=str(e),
        error_type=type(e).__name__,
        context=context or {},
        exc_info=True,
    )

    return UnifiedToolOutput.failure(
        message=APIMessages.internal_error(type(e).__name__),
        error_code="INTERNAL_ERROR",
        metadata={
            FIELD_ERROR_TYPE: type(e).__name__,
            FIELD_ERROR_MESSAGE: str(e),
        },
    )


def extract_session_id_from_state(
    state: dict[str, Any],
    context_name: str = "unknown",
) -> str:
    """
    Extract and validate session_id from LangGraph state dict.

    CRITICAL FIX (BUG-002): Ensures session_id is present for Store namespace consistency.
    Store operations use namespace (user_id, session_id, context, domain) - missing
    session_id creates broken namespaces or inconsistent data isolation.

    This helper is for use in NODES (task_orchestrator, planner, etc.) that work with
    State dict rather than ToolRuntime. For tools, use validate_runtime_config() instead.

    Args:
        state: LangGraph state dict with session_id key
        context_name: Name of calling node/context (for error messages)

    Returns:
        session_id string

    Raises:
        ValueError: If session_id is missing or empty

    Example:
        >>> # In a node function
        >>> from src.domains.agents.constants import STATE_KEY_SESSION_ID
        >>> session_id = extract_session_id_from_state(state, "task_orchestrator")
        >>> # session_id is guaranteed to be non-empty string
    """
    from src.domains.agents.constants import STATE_KEY_SESSION_ID

    session_id = state.get(STATE_KEY_SESSION_ID, "")
    if not session_id:
        error_msg = (
            f"{context_name}: session_id missing in state['{STATE_KEY_SESSION_ID}']. "
            f"This is a critical error - session_id is required for Store namespace consistency. "
            f"Ensure session_id is set in initial state creation."
        )
        logger.error(
            "session_id_missing_critical_error",
            context=context_name,
            error=error_msg,
        )
        raise ValueError(error_msg)

    return session_id


# =============================================================================
# CACHE METADATA EXTRACTION
# =============================================================================


def extract_cache_metadata(result: dict[str, Any]) -> tuple[bool, Any]:
    """
    Extract cache metadata from API result dict.

    Centralizes the cache metadata extraction pattern that appears across
    multiple tools (SearchContactsTool, ListContactsTool, SearchEmailsTool, etc.).

    Args:
        result: API result dictionary that may contain cache metadata

    Returns:
        Tuple of (from_cache: bool, cached_at: Optional[datetime string])

    Example:
        >>> result = await client.search_contacts(query)
        >>> from_cache, cached_at = extract_cache_metadata(result)
    """
    from src.core.field_names import FIELD_CACHED_AT

    return result.get("from_cache", False), result.get(FIELD_CACHED_AT)


# =============================================================================
# USER PREFERENCES LOOKUP
# =============================================================================


async def get_user_preferences(runtime: ToolRuntime) -> tuple[str, str, str]:
    """
    Get user timezone, language and locale from database with defaults.

    Centralizes the user preferences lookup pattern that appears in tools
    that need to format dates/times according to user settings.

    Args:
        runtime: ToolRuntime containing user_id in config

    Returns:
        Tuple of (timezone: str, language: str, locale: str)
        Defaults: ("UTC", "fr", "fr-FR")

    Example:
        >>> timezone, language, locale = await get_user_preferences(runtime)
        >>> formatted_date = format_date(email_date, timezone, locale)
    """
    user_timezone = "UTC"
    user_language = "fr"
    locale = "fr-FR"

    try:
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        if user_id_raw:
            user_id = parse_user_id(user_id_raw)
            from src.domains.users.service import UserService
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                user_service = UserService(db)
                user = await user_service.get_user_by_id(user_id)
                if user:
                    user_timezone = user.timezone if user.timezone else "UTC"
                    user_language = user.language if user.language else "fr"
                    locale = f"{user_language}-{user_language.upper()}"
                    logger.debug(
                        "get_user_preferences_success",
                        user_id=str(user_id),
                        timezone=user_timezone,
                        language=user_language,
                        locale=locale,
                    )
    except Exception as e:
        logger.warning(
            "get_user_preferences_error",
            error=str(e),
            error_type=type(e).__name__,
        )

    return user_timezone, user_language, locale


async def get_user_language_safe(
    runtime: ToolRuntime,
    default: str = settings.default_language,
) -> str:
    """Get user language from runtime preferences with safe fallback.

    Eliminates the repeated try-except pattern found in 7+ tool methods
    that only need the language code from user preferences.

    Args:
        runtime: LangGraph ToolRuntime configuration
        default: Fallback language if preferences unavailable

    Returns:
        User language code (e.g., "fr", "en") or default

    Example:
        >>> language = await get_user_language_safe(self.runtime)
        >>> # Instead of:
        >>> # language = settings.default_language
        >>> # try:
        >>> #     _, language, _ = await get_user_preferences(self.runtime)
        >>> # except Exception:
        >>> #     pass
    """
    try:
        _, language, _ = await get_user_preferences(runtime)
        return language
    except (ValueError, KeyError, RuntimeError, AttributeError) as e:
        logger.debug("user_language_fallback", error=str(e))
        return default


# =============================================================================
# CONTEXT STORE HELPERS
# =============================================================================


async def save_to_context_store(
    runtime: ToolRuntime,
    domain: str,
    key: str,
    value: Any,
    context_type: str = "context",
) -> None:
    """
    Save result to runtime.store with automatic user/thread scoping.

    Centralizes the context store saving pattern that appears in tools
    that need to persist results for conversation context.

    IMPORTANT: Uses async store methods (aput) - do not use sync methods.

    Args:
        runtime: ToolRuntime with store and config
        domain: Domain identifier (e.g., "gmail", "contacts", "calendar")
        key: Key for the stored value (e.g., "list", "details")
        value: Value to store (must be JSON-serializable)
        context_type: Context type in namespace (default: "context")

    Example:
        >>> await save_to_context_store(
        ...     runtime,
        ...     domain="gmail",
        ...     key="list",
        ...     value={"emails": emails_list, "query": query}
        ... )
    """
    if not runtime.store:
        return

    try:
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        thread_id = runtime.config.get("configurable", {}).get("thread_id")

        if user_id_raw and thread_id:
            user_id = parse_user_id(user_id_raw)
            await runtime.store.aput(
                (str(user_id), str(thread_id), context_type, domain),
                key,
                value,
            )
    except Exception:
        pass  # Context save is non-critical


# =============================================================================
# DATA EXTRACTION HELPERS
# =============================================================================


def extract_value(obj: Any, *keys, default: Any = None) -> Any:
    """
    Extract value from Pydantic model, dict, or nested structure.

    Centralizes the polymorphic data extraction pattern that appears in
    handlers and tools that need to handle both Pydantic models and dicts.

    Args:
        obj: Source object (Pydantic model or dict)
        *keys: Sequence of keys to traverse (strings or ints for list access)
        default: Default value if path not found

    Returns:
        Value at the specified path, or default

    Example:
        >>> # Works with both Pydantic models and dicts
        >>> email = extract_value(contact, "emailAddresses", 0, "value")
        >>> # Same as: contact.emailAddresses[0].value or contact["emailAddresses"][0]["value"]
    """
    current = obj

    for key in keys:
        if current is None:
            return default

        # Handle integer keys for list access
        if isinstance(key, int):
            if isinstance(current, list | tuple) and 0 <= key < len(current):
                current = current[key]
            else:
                return default
        # Try attribute access (Pydantic models)
        elif hasattr(current, str(key)):
            current = getattr(current, str(key))
        # Try dict access
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return default

    return current if current is not None else default


def extract_value_by_path(obj: Any, path: str, default: Any = None) -> Any:
    """
    Extract value from nested structure using dot-notation path string.

    Wrapper around extract_value() that accepts a path string instead of *keys.
    Supports:
    - Simple paths: "name"
    - Nested paths: "start.dateTime"
    - Array indices: "names.0.displayName" (0 is converted to int)

    Args:
        obj: Source object (Pydantic model or dict)
        path: Dot-separated path string (e.g., "names.0.displayName")
        default: Default value if path not found

    Returns:
        Value at the specified path, or default

    Example:
        >>> extract_value_by_path(contact, "emailAddresses.0.value")
        "john@example.com"
        >>> extract_value_by_path(event, "start.dateTime")
        "2026-01-30T10:00:00Z"
    """
    if not path:
        return default

    # Convert path to keys, parsing integers for array access
    keys: list[str | int] = []
    for part in path.split("."):
        try:
            keys.append(int(part))
        except ValueError:
            keys.append(part)

    return extract_value(obj, *keys, default=default)


# =============================================================================
# CONNECTOR PREFERENCES HELPERS
# =============================================================================


async def get_connector_preference(
    runtime: ToolRuntime,
    connector_type: str,
    preference_name: str,
    default: str | None = None,
) -> str | None:
    """
    Get a user's connector preference value (decrypted).

    Centralizes the connector preference lookup pattern for tools that need
    to read user-configured defaults (e.g., default calendar name, default task list).

    Args:
        runtime: ToolRuntime containing user_id and dependencies in config
        connector_type: Connector type string (e.g., "google_calendar", "google_tasks")
        preference_name: Name of the preference field (e.g., "default_calendar_name")
        default: Default value if preference not set or lookup fails

    Returns:
        Preference value or default

    Example:
        >>> # In a calendar tool
        >>> default_calendar = await get_connector_preference(
        ...     runtime,
        ...     "google_calendar",
        ...     "default_calendar_name",
        ...     default=None
        ... )
        >>> if default_calendar:
        ...     # Use user's preferred calendar
        ...     calendar_id = await resolve_calendar_by_name(client, default_calendar)
    """
    try:
        from src.domains.agents.dependencies import get_dependencies
        from src.domains.connectors.models import ConnectorType
        from src.domains.connectors.preferences import ConnectorPreferencesService
        from src.domains.connectors.repository import ConnectorRepository

        # Get user_id from runtime config
        user_id_raw = runtime.config.get("configurable", {}).get("user_id")
        if not user_id_raw:
            return default

        user_id = parse_user_id(user_id_raw)

        # Get ToolDependencies from runtime
        deps = get_dependencies(runtime)

        # Get connector by user and type
        repository = ConnectorRepository(deps.db)

        # Convert string to ConnectorType enum
        try:
            connector_type_enum = ConnectorType(connector_type)
        except ValueError:
            logger.warning(
                "get_connector_preference_invalid_type",
                connector_type=connector_type,
            )
            return default

        connector = await repository.get_by_user_and_type(user_id, connector_type_enum)
        if not connector:
            return default

        # Get preference value using service
        return ConnectorPreferencesService.get_preference_value(
            connector_type,
            connector.preferences_encrypted,
            preference_name,
            default,
        )

    except Exception as e:
        logger.warning(
            "get_connector_preference_failed",
            connector_type=connector_type,
            preference_name=preference_name,
            error=str(e),
        )
        return default


async def resolve_connector_default(
    runtime: ToolRuntime,
    connector_type: str,
    preference_name: str,
    client: Any,
    resolver_func: Any,
    fallback_id: str,
) -> str:
    """
    Resolve user's connector preference name to API ID (case-insensitive).

    Combines preference lookup with case-insensitive resolution:
    1. Gets user's configured preference name (e.g., "Famille" for calendar)
    2. Resolves name to API ID using case-insensitive matching
    3. Falls back to default ID if name not found

    Args:
        runtime: ToolRuntime containing user_id and dependencies
        connector_type: Connector type (e.g., "google_calendar", "google_tasks")
        preference_name: Preference field name (e.g., "default_calendar_name")
        client: API client instance (GoogleCalendarClient, GoogleTasksClient)
        resolver_func: Async resolver function (resolve_calendar_name, resolve_task_list_name)
        fallback_id: Fallback ID if preference not set or resolution fails

    Returns:
        Resolved API ID or fallback_id

    Example:
        >>> from src.domains.connectors.preferences import resolve_calendar_name
        >>> calendar_id = await resolve_connector_default(
        ...     runtime,
        ...     "google_calendar",
        ...     "default_calendar_name",
        ...     client,
        ...     resolve_calendar_name,
        ...     fallback_id="primary",
        ... )
        >>> # User configured "famille" -> resolves to ID of "Famille" calendar
    """
    try:
        # Get user's configured preference name
        preference_value = await get_connector_preference(
            runtime,
            connector_type,
            preference_name,
            default=None,
        )

        if not preference_value:
            return fallback_id

        # Resolve name to ID (case-insensitive)
        resolved_id = await resolver_func(client, preference_value, fallback=fallback_id)
        return resolved_id

    except Exception as e:
        logger.warning(
            "resolve_connector_default_failed",
            connector_type=connector_type,
            preference_name=preference_name,
            error=str(e),
        )
        return fallback_id


# =============================================================================
# LOCATION RESOLUTION HELPERS
# =============================================================================


class ResolvedLocation(NamedTuple):
    """Resolved location data for tools (weather, places)."""

    lat: float
    lon: float
    source: str  # "browser", "home", "explicit"
    address: str | None = None


def get_original_user_message(runtime: ToolRuntime) -> str:
    """
    Get original user message from runtime config.

    The user message is passed from AgentService through
    RunnableConfig.configurable["__user_message"].

    This is useful for tools that need to detect location phrases
    like "chez moi" or "nearby" in the original query.

    Args:
        runtime: ToolRuntime containing config with user message

    Returns:
        Original user message string, or empty string if not available

    Example:
        >>> user_msg = get_original_user_message(runtime)
        >>> if "chez moi" in user_msg.lower():
        ...     # Use home location
    """
    try:
        return (runtime.config.get("configurable") or {}).get("__user_message", "")
    except Exception:
        return ""


def extract_coordinates(
    location: dict[str, Any] | object | None,
) -> tuple[float | None, float | None]:
    """
    Extract latitude and longitude from a location dict or object.

    Handles multiple key naming conventions:
    - lat/lon (common shorthand)
    - latitude/longitude (full names)
    - lng (Google API convention for longitude)

    This centralizes coordinate extraction to avoid DRY violations
    across tools (routes, places, etc).

    Args:
        location: Dict or object with coordinate fields, or None

    Returns:
        Tuple of (latitude, longitude), both None if not found

    Examples:
        >>> extract_coordinates({"lat": 48.8566, "lon": 2.3522})
        (48.8566, 2.3522)

        >>> extract_coordinates({"latitude": 48.8566, "longitude": 2.3522})
        (48.8566, 2.3522)

        >>> extract_coordinates({"lat": 48.8566, "lng": 2.3522})
        (48.8566, 2.3522)

        >>> extract_coordinates(None)
        (None, None)
    """
    if location is None:
        return None, None

    # Handle dict
    if isinstance(location, dict):
        lat = location.get("lat") or location.get("latitude")
        lon = location.get("lon") or location.get("lng") or location.get("longitude")
        return lat, lon

    # Handle object with attributes
    if hasattr(location, "lat"):
        lat = getattr(location, "lat", None)
        lon = getattr(location, "lon", None) or getattr(location, "lng", None)
        return lat, lon

    if hasattr(location, "latitude"):
        lat = getattr(location, "latitude", None)
        lon = getattr(location, "longitude", None)
        return lat, lon

    return None, None


async def get_browser_geolocation(runtime: ToolRuntime) -> ResolvedLocation | None:
    """
    Get browser geolocation from runtime config.

    The browser context is passed from frontend through ChatRequest.context
    and propagated to RunnableConfig.configurable["__browser_context"].

    Args:
        runtime: ToolRuntime containing config with browser context

    Returns:
        ResolvedLocation if geolocation available, None otherwise

    Example:
        >>> geoloc = await get_browser_geolocation(runtime)
        >>> if geoloc:
        ...     print(f"User is at {geoloc.lat}, {geoloc.lon}")
    """
    try:
        browser_context = (runtime.config.get("configurable") or {}).get("__browser_context")
        if not browser_context:
            return None

        # Handle both BrowserContext object and dict
        geolocation = None
        if hasattr(browser_context, "geolocation"):
            geolocation = browser_context.geolocation
        elif isinstance(browser_context, dict):
            geolocation = browser_context.get("geolocation")

        if not geolocation:
            return None

        # Extract coordinates (handle both object and dict)
        if hasattr(geolocation, "lat"):
            lat = geolocation.lat
            lon = geolocation.lon
        else:
            lat = geolocation.get("lat")
            lon = geolocation.get("lon")

        if lat is None or lon is None:
            return None

        return ResolvedLocation(
            lat=float(lat),
            lon=float(lon),
            source="browser",
            address=None,
        )

    except Exception as e:
        logger.warning(
            "get_browser_geolocation_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def get_user_home_location(runtime: ToolRuntime) -> ResolvedLocation | None:
    """
    Get user's configured home location from database (decrypted).

    Retrieves the encrypted home location from the User model and decrypts it
    for use in location-aware tools.

    Args:
        runtime: ToolRuntime containing user_id in config

    Returns:
        ResolvedLocation if home location configured, None otherwise

    Example:
        >>> home = await get_user_home_location(runtime)
        >>> if home:
        ...     print(f"Home is at {home.address}")
    """
    try:
        user_id_raw = (runtime.config.get("configurable") or {}).get("user_id")
        if not user_id_raw:
            logger.warning("get_user_home_location_no_user_id")
            return None

        user_id = parse_user_id(user_id_raw)

        from src.domains.users.service import UserService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            user_service = UserService(db)
            home_location = await user_service.get_home_location(user_id)

            if not home_location:
                logger.info(
                    "get_user_home_location_not_configured",
                    user_id=str(user_id),
                )
                return None

            logger.info(
                "get_user_home_location_found",
                user_id=str(user_id),
                address_preview=home_location.address[:30] if home_location.address else None,
                lat=home_location.lat,
                lon=home_location.lon,
            )
            return ResolvedLocation(
                lat=home_location.lat,
                lon=home_location.lon,
                source="home",
                address=home_location.address,
            )

    except Exception as e:
        logger.warning(
            "get_user_home_location_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def resolve_location(
    runtime: ToolRuntime,
    user_message: str,
    language: str = "fr",
) -> tuple[ResolvedLocation | None, str | None]:
    """
    Resolve location for tools based on user message and available sources.

    Main location resolution function that combines phrase detection with
    location source lookup. Priority depends on detected location type:

    - HOME: Home location > Browser geolocation > Fallback message
    - CURRENT: Browser geolocation only > Fallback message
    - EXPLICIT: Return None (let tool geocode the explicit location)
    - NONE: Browser geolocation > Home location > None (silent fallback)

    Args:
        runtime: ToolRuntime with config and user context
        user_message: User's message to analyze for location references
        language: Language code for phrase detection (default: "fr")

    Returns:
        Tuple of (ResolvedLocation | None, fallback_message | None)
        - If location found: (location, None)
        - If location needed but not found: (None, fallback_message)
        - If explicit location: (None, None) - let tool handle geocoding

    Example:
        >>> location, fallback = await resolve_location(runtime, "météo chez moi", "fr")
        >>> if location:
        ...     weather = await get_weather(location.lat, location.lon)
        >>> elif fallback:
        ...     return fallback  # Ask user for location
    """
    from src.domains.agents.utils.i18n_location import (
        LocationType,
        detect_location_type,
        get_fallback_message,
    )

    location_type = detect_location_type(user_message, language)

    logger.debug(
        "resolve_location_type_detected",
        location_type=location_type.value,
        user_message_preview=user_message[:50] if user_message else "",
        language=language,
    )

    # Get available location sources
    browser_geoloc = await get_browser_geolocation(runtime)
    home_location = await get_user_home_location(runtime)

    match location_type:
        case LocationType.HOME:
            # User explicitly references home ("chez moi", "at home")
            # Priority: home > browser > fallback
            if home_location:
                logger.info(
                    "resolve_location_using_home",
                    has_home=True,
                    address_preview=home_location.address[:30] if home_location.address else None,
                )
                return (home_location, None)

            if browser_geoloc:
                logger.info(
                    "resolve_location_home_fallback_to_browser",
                    reason="No home configured, using browser geolocation",
                )
                return (browser_geoloc, None)

            # No location available for HOME reference
            logger.warning(
                "resolve_location_home_no_source",
                has_browser=False,
                has_home=False,
            )
            return (None, get_fallback_message(language))

        case LocationType.CURRENT:
            # User explicitly references current position ("nearby", "around me")
            # Priority: browser only > fallback
            if browser_geoloc:
                logger.info(
                    "resolve_location_using_browser",
                    lat=browser_geoloc.lat,
                    lon=browser_geoloc.lon,
                )
                return (browser_geoloc, None)

            # No browser geolocation for CURRENT reference
            logger.warning(
                "resolve_location_current_no_browser",
                has_home=home_location is not None,
            )
            return (None, get_fallback_message(language))

        # Note: LocationType.EXPLICIT was removed in 2026-01 cleanup.
        # Explicit location extraction is now handled by the planner via the
        # 'location' parameter in tool manifests. When planner provides location,
        # resolve_location() is not called at all.

        case LocationType.NONE:
            # No location reference detected - use implicit location
            # Priority: browser > home > None (silent, no fallback message)
            if browser_geoloc:
                logger.debug(
                    "resolve_location_implicit_browser",
                    lat=browser_geoloc.lat,
                    lon=browser_geoloc.lon,
                )
                return (browser_geoloc, None)

            if home_location:
                logger.debug(
                    "resolve_location_implicit_home",
                    address_preview=home_location.address[:30] if home_location.address else None,
                )
                return (home_location, None)

            # No implicit location available - silent (tools may have their own fallback)
            logger.debug("resolve_location_implicit_none")
            return (None, None)

    # Should not reach here, but return None for safety
    return (None, None)


# =============================================================================
# CONTACT RESOLUTION HELPERS
# =============================================================================


async def resolve_contact_to_email(
    runtime: ToolRuntime,
    name: str,
) -> str | None:
    """
    Resolve a contact name to email address using Google Contacts.

    This is a centralized helper for tools that need to convert a contact
    name (e.g., "Jean Dupont", "Jane Smith") to an email address.

    Uses Google People API searchContacts to find matching contacts
    and extracts the primary email.

    Args:
        runtime: ToolRuntime with config containing user_id and dependencies
        name: Contact name to resolve

    Returns:
        Email address if found, None otherwise

    Example:
        >>> email = await resolve_contact_to_email(runtime, "Jean Dupont")
        >>> if email:
        ...     # Use email for send_email_tool
        ...     pass

    Note:
        This function is fail-safe - it returns None on any error
        rather than raising exceptions. Tools should handle None
        gracefully (e.g., by using the original name for validation error).
    """
    from src.core.constants import CONTACT_RESOLUTION_MAX_RESULTS
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    if not runtime or not runtime.config:
        return None

    try:
        configurable = runtime.config.get("configurable", {})
        deps = configurable.get("__deps")
        user_id_raw = configurable.get("user_id")

        if not deps or not user_id_raw:
            return None

        user_uuid = parse_user_id(user_id_raw)

        # Resolve active contacts provider (Google or Apple) dynamically
        try:
            client, _resolved_type = await resolve_client_for_category("contacts", user_uuid, deps)
        except Exception:
            logger.debug(
                "resolve_contact_to_email_no_connector",
                name=name,
            )
            return None

        # Search for contact
        # search_contacts returns {"results": [...], "totalItems": N}
        response = await client.search_contacts(
            query=name, max_results=CONTACT_RESOLUTION_MAX_RESULTS
        )
        results = response.get("results", [])

        if not results:
            logger.debug(
                "resolve_contact_to_email_not_found",
                name=name,
            )
            return None

        # Find first contact with an email
        # Structure: results[].person.emailAddresses[].value
        for result in results:
            person = result.get("person", {})
            emails = person.get("emailAddresses", [])
            if emails:
                email = emails[0].get("value")
                if email:
                    display_name = (
                        person.get("names", [{}])[0].get("displayName")
                        if person.get("names")
                        else None
                    )
                    logger.info(
                        "resolve_contact_to_email_success",
                        name=name,
                        contact_name=display_name,
                        email=email,
                    )
                    return email

        logger.debug(
            "resolve_contact_to_email_no_email_field",
            name=name,
            results_count=len(results),
        )
        return None

    except Exception as e:
        logger.warning(
            "resolve_contact_to_email_error",
            name=name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def resolve_recipients_to_emails(
    runtime: ToolRuntime | None,
    recipients: str | list[str] | None,
    field_name: str = "recipient",
) -> str | list[str] | None:
    """
    Resolve recipient names to email addresses using Google Contacts.

    Centralized helper for both email tools (string input) and calendar tools (list input).
    For each recipient that is not already a valid email, attempts to resolve it
    via Google People API.

    Feature Toggle:
        Controlled by settings.recipient_resolution_enabled (default: True).
        When disabled, returns recipients unchanged (requires explicit emails).

    Args:
        runtime: ToolRuntime with config containing user_id and dependencies
        recipients: Either a comma-separated string (email tools) or list of strings (calendar)
        field_name: Field name for logging (e.g., "to", "cc", "attendees")

    Returns:
        - If input is string: returns resolved string (comma-separated, RFC 5322 format)
        - If input is list: returns list of resolved emails
        - If input is None/empty: returns None

    Examples:
        >>> # Email tool - string input
        >>> resolved = await resolve_recipients_to_emails(runtime, "Jane Smith", "to")
        >>> # Returns: "Jane Smith <jane.smith@example.com>"

        >>> # Calendar tool - list input
        >>> resolved = await resolve_recipients_to_emails(runtime, ["Jane Smith", "test@example.com"], "attendees")
        >>> # Returns: ["jane.smith@example.com", "test@example.com"]

    Note:
        - Uses validate_email from src.core.validators for consistent email validation
        - For strings: formats as "Name <email>" per RFC 5322
        - For lists: returns plain emails (Google Calendar API format)
        - Fail-safe: unresolved names are kept as-is (will fail at API level with clear error)
    """
    from src.core.validators import validate_email

    if not recipients:
        return None

    if not runtime:
        return recipients  # Can't resolve without runtime

    # Handle string input (email tools: to, cc, bcc)
    if isinstance(recipients, str):
        # Split by comma for potential multiple recipients
        parts = [p.strip() for p in recipients.split(",") if p.strip()]

        # Check if first part is already a valid email (all are likely emails too)
        if parts and validate_email(parts[0]):
            return recipients  # Already valid, no resolution needed

        # Resolve each name individually
        resolved_parts: list[str] = []
        for name in parts:
            resolved_email = await resolve_contact_to_email(runtime, name)
            if resolved_email:
                # Format as "Name <email>" for RFC 5322 compliance
                formatted = f"{name} <{resolved_email}>"
                logger.info(
                    "recipient_resolved_to_email",
                    field=field_name,
                    original=name,
                    resolved=resolved_email,
                    formatted=formatted,
                )
                resolved_parts.append(formatted)
            else:
                # Couldn't resolve - keep original (will fail at validation)
                logger.warning(
                    "recipient_resolution_failed",
                    field=field_name,
                    recipient=name,
                )
                resolved_parts.append(name)

        return ", ".join(resolved_parts)

    # Handle list input (calendar tools: attendees)
    if isinstance(recipients, list):
        resolved_list: list[str] = []

        for recipient in recipients:
            recipient = recipient.strip()
            if not recipient:
                continue

            # Check if already a valid email
            if validate_email(recipient):
                resolved_list.append(recipient)
                continue

            # Try to resolve
            resolved_email = await resolve_contact_to_email(runtime, recipient)
            if resolved_email:
                logger.info(
                    "recipient_resolved_to_email",
                    field=field_name,
                    original=recipient,
                    resolved=resolved_email,
                )
                resolved_list.append(resolved_email)
            else:
                # Keep original - will fail at API level with clear error
                logger.warning(
                    "recipient_resolution_failed",
                    field=field_name,
                    recipient=recipient,
                )
                resolved_list.append(recipient)

        return resolved_list

    return recipients


# =============================================================================
# SIDE-CHANNEL SSE EMISSION
# =============================================================================


def emit_side_channel_chunk(
    runtime: ToolRuntime | None,
    chunk: Any,
) -> None:
    """Put a ChatStreamChunk into the side-channel queue for direct SSE emission.

    This is the generic mechanism for any tool to emit SSE events directly to the
    frontend without going through the LLM response. The chunk is yielded as-is by
    the SSE generator in service.py.

    Fire-and-forget. Never raises — silently drops the chunk if the queue is
    unavailable (e.g., running outside graph context, or in tests).

    Args:
        runtime: Tool runtime for accessing configurable queue. None-safe.
        chunk: A ChatStreamChunk instance to emit. Must be fully constructed by caller.
    """
    try:
        configurable = (runtime.config.get("configurable") or {}) if runtime else {}
        queue = configurable.get("__side_channel_queue")
        if queue is not None:
            queue.put_nowait(chunk)
    except Exception:
        pass


__all__ = [
    "ResolvedLocation",
    "ValidatedRuntimeConfig",
    "extract_cache_metadata",
    "extract_coordinates",
    "extract_session_id_from_state",
    "extract_value",
    "get_browser_geolocation",
    "get_connector_preference",
    "get_original_user_message",
    "get_user_home_location",
    "get_user_language_safe",
    "get_user_preferences",
    "handle_connector_api_error",
    "handle_tool_exception",
    "parse_user_id",
    "resolve_connector_default",
    "resolve_contact_to_email",
    "resolve_location",
    "resolve_recipients_to_emails",
    "save_to_context_store",
    "emit_side_channel_chunk",
    "validate_runtime_config",
]
