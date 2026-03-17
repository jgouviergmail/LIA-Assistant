"""
Tool Dependencies Container for Agent Tools.

This module provides a dependency injection mechanism for LangChain tools,
allowing them to share database sessions and service instances across
a single graph execution without repeatedly opening new connections.

Architecture:
- ToolDependencies: Container class holding shared resources (DB session, services, clients)
- get_dependencies(): Helper to extract dependencies from ToolRuntime
- Resources are lazy-initialized and cached for the duration of graph execution
- Concurrency-safe: Uses asyncio.Lock to prevent SQLAlchemy race conditions

Usage in tools:
    @tool
    async def my_tool(
        arg: str,
        runtime: Annotated[ToolRuntime, InjectedToolArg],
    ) -> str:
        deps = get_dependencies(runtime)
        connector_service = await deps.get_connector_service()
        client = await deps.get_or_create_client(...)

Usage in graph execution:
    async with get_db_context() as db:
        deps = ToolDependencies(db_session=db)
        config = {
            "configurable": {
                "user_id": str(user_id),
                "__deps": deps,  # Inject dependencies
            }
        }
        async for chunk in agent.astream(state, config):
            yield chunk
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials, ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.infrastructure.observability.metrics_agents import (
    contacts_cache_hits,
    contacts_cache_misses,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ConcurrencySafeConnectorService:
    """
    Thread-safe wrapper for ConnectorService.

    Delegates all method calls to the underlying ConnectorService but
    serializes DB access using asyncio.Lock to prevent SQLAlchemy
    concurrent operations errors.

    This wrapper is transparent to tools - they call methods normally,
    but all DB operations are automatically serialized.
    """

    def __init__(self, service: ConnectorService, lock: asyncio.Lock) -> None:
        """
        Initialize wrapper.

        Args:
            service: Underlying ConnectorService instance
            lock: Shared asyncio.Lock for serializing DB operations
        """
        self._service = service
        self._lock = lock

    async def get_connector_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> ConnectorCredentials | None:
        """Thread-safe wrapper for get_connector_credentials (OAuth connectors)."""
        async with self._lock:
            return await self._service.get_connector_credentials(user_id, connector_type)

    async def get_api_key_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> APIKeyCredentials | None:
        """Thread-safe wrapper for get_api_key_credentials (API key connectors)."""
        async with self._lock:
            return await self._service.get_api_key_credentials(user_id, connector_type)

    async def is_connector_active(self, user_id: UUID, connector_type: ConnectorType) -> bool:
        """Thread-safe wrapper for is_connector_active.

        Without this, concurrent tool executions (e.g., parallel sub-agent steps)
        cause 'concurrent operations are not permitted' errors because
        is_connector_active performs a DB query through the repository.
        """
        async with self._lock:
            return await self._service.is_connector_active(user_id, connector_type)

    def __getattr__(self, name: str) -> Any:
        """
        Fallback for any other methods.

        For methods not explicitly wrapped, delegate directly to service.
        This maintains backward compatibility while protecting critical paths.
        """
        return getattr(self._service, name)


class ToolDependencies:
    """
    Container for tool dependencies injected at graph execution.

    Manages shared resources across all tool calls within a single graph execution:
    - Database session (reused for all DB operations)
    - ConnectorService (singleton per execution)
    - API clients (cached by type/user)
    - Concurrency control via asyncio.Lock to prevent SQLAlchemy race conditions

    This eliminates the overhead of opening new DB sessions and instantiating
    services for every single tool call.

    Thread Safety:
        SQLAlchemy AsyncSession does not support concurrent operations.
        This class uses an asyncio.Lock to serialize DB access when multiple
        tools execute in parallel (e.g., during HITL approval of multiple actions).
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """
        Initialize dependencies container.

        Args:
            db_session: Shared database session for this graph execution
        """
        self._db = db_session
        self._connector_service: ConcurrencySafeConnectorService | None = None
        self._clients_cache: dict[Any, Any] = {}
        self._db_lock = asyncio.Lock()  # Serialize concurrent DB access

        logger.debug(
            "tool_dependencies_initialized",
            db_session_id=id(db_session),
        )

    @property
    def db(self) -> AsyncSession:
        """Get the shared database session."""
        return self._db

    async def get_connector_service(self) -> ConcurrencySafeConnectorService:
        """
        Get or create singleton ConnectorService with concurrency protection.

        The service is lazy-initialized on first access and reused
        for all subsequent calls within this graph execution.

        Returns a ConcurrencySafeConnectorService wrapper that automatically
        serializes all DB operations to prevent SQLAlchemy concurrent access errors.

        Returns:
            Thread-safe ConnectorService wrapper

        Note:
            This method is thread-safe for concurrent tool execution.
            The returned wrapper ensures all DB operations are serialized,
            preventing "concurrent operations are not permitted" errors.
        """
        if self._connector_service is None:
            # Create underlying service without lock (no DB access yet)
            underlying_service = ConnectorService(self._db)
            # Wrap with concurrency protection
            self._connector_service = ConcurrencySafeConnectorService(
                underlying_service, self._db_lock
            )
            logger.debug(
                "connector_service_initialized",
                service_id=id(self._connector_service),
                wrapped=True,
            )
        return self._connector_service

    async def get_or_create_client(
        self,
        client_class: type[T],
        cache_key: Any,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        """
        Get or create cached API client with concurrency protection.

        Generic caching mechanism for API clients (Google People, Gmail, etc.).
        Clients are lazy-initialized and cached by a composite key.

        Uses asyncio.Lock to prevent race conditions during client creation
        (factory may access DB to fetch credentials).

        Args:
            client_class: Client class type (for type safety)
            cache_key: Unique cache key (e.g., (user_id, connector_type))
            factory: Async factory function to create client if not cached

        Returns:
            Cached or newly created client instance

        Example:
            client = await deps.get_or_create_client(
                GooglePeopleClient,
                cache_key=(user_id, ConnectorType.GOOGLE_CONTACTS),
                factory=lambda: create_google_people_client(user_id, credentials),
            )

        Note:
            This method is thread-safe for concurrent tool execution.
            The lock ensures factory execution is serialized if it accesses DB.
        """
        # Fast path: return cached client without lock if already exists
        if cache_key in self._clients_cache:
            # Track cache hit (client reused)
            cache_type = self._get_cache_type(cache_key)
            contacts_cache_hits.labels(cache_type=cache_type).inc()

            logger.debug(
                "reusing_cached_client",
                client_class=client_class.__name__,
                cache_key=str(cache_key),
                cache_type=cache_type,
            )
            cached_client: T = self._clients_cache[cache_key]
            return cached_client

        # Slow path: create client with lock protection
        async with self._db_lock:
            # Double-check pattern: another coroutine may have created it
            if cache_key not in self._clients_cache:
                # Track cache miss (client created)
                cache_type = self._get_cache_type(cache_key)
                contacts_cache_misses.labels(cache_type=cache_type).inc()

                logger.debug(
                    "creating_client",
                    client_class=client_class.__name__,
                    cache_key=str(cache_key),
                    cache_type=cache_type,
                )
                self._clients_cache[cache_key] = await factory()

        created_client: T = self._clients_cache[cache_key]
        return created_client

    def _get_cache_type(self, cache_key: Any) -> str:
        """
        Extract cache type label from cache_key for metrics.

        Maps ConnectorType to a functional category label (provider-agnostic).
        E.g., both GOOGLE_CONTACTS and APPLE_CONTACTS → "contacts".

        Args:
            cache_key: Cache key tuple (user_id, connector_type)

        Returns:
            String label for cache_type: "contacts", "email", "calendar", etc.
        """
        # cache_key is typically (UUID, ConnectorType)
        if isinstance(cache_key, tuple) and len(cache_key) >= 2:
            connector_type = cache_key[1]
            if isinstance(connector_type, ConnectorType):
                # Use functional category for provider-agnostic labels
                from src.domains.connectors.models import get_functional_category

                category = get_functional_category(connector_type)
                if category:
                    return category  # "email", "calendar", "contacts"
                # Fallback for types without a category (drive, tasks, etc.)
                return str(connector_type.value).lower()
        return "unknown"

    def clear_cache(self) -> None:
        """
        Clear all cached clients.

        Useful for testing or forcing client recreation.
        Note: Does not close DB session or reset ConnectorService.
        """
        logger.debug(
            "clearing_client_cache",
            cached_clients_count=len(self._clients_cache),
        )
        self._clients_cache.clear()


def get_dependencies(runtime: ToolRuntime) -> ToolDependencies:
    """
    Extract dependencies from ToolRuntime config.

    Retrieves the ToolDependencies instance injected into runtime.config
    during graph execution. Raises RuntimeError if dependencies not found.

    Args:
        runtime: LangChain ToolRuntime instance (auto-injected in tools)

    Returns:
        ToolDependencies container with shared resources

    Raises:
        RuntimeError: If dependencies not injected in runtime.config

    Example:
        @tool
        async def my_tool(runtime: Annotated[ToolRuntime, InjectedToolArg]) -> str:
            deps = get_dependencies(runtime)
            db = deps.db
            service = await deps.get_connector_service()
    """
    deps = runtime.config.get("configurable", {}).get("__deps")
    if not deps:
        logger.error(
            "tool_dependencies_not_found",
            config_keys=list(runtime.config.get("configurable", {}).keys()),
        )
        raise RuntimeError(
            "ToolDependencies not injected in runtime.config. "
            "Ensure dependencies are added during graph execution:\n"
            "  deps = ToolDependencies(db_session=db)\n"
            '  config = {"configurable": {"__deps": deps}}'
        )
    # Type assertion: we validated deps is ToolDependencies via the if check above
    assert isinstance(deps, ToolDependencies), "Expected ToolDependencies instance"
    return deps
