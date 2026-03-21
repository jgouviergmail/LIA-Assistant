"""
Base classes for agent tools.

This module provides abstract base classes that eliminate boilerplate code
and standardize patterns across all connector tools.

Design Philosophy:
- DRY (Don't Repeat Yourself): Extract common patterns used by all tools
- Type Safety: Leverage Pydantic for input/output validation
- Dependency Injection: Built-in support for ToolDependencies pattern
- Error Handling: Standardized error handling and metrics tracking
- Future-proof: Generic enough to support new agents/connectors
- Registry-Ready: Dual-mode output (legacy str or UnifiedToolOutput)

Architecture:
- ConnectorTool: Base class for all connector-based tools (Google, Microsoft, etc.)
- Handles: DI, OAuth, error handling, metrics, caching, response formatting
- ToolOutputMixin: Optional mixin for data registry support

Usage Example:
    class GoogleContactsTool(ConnectorTool):
        connector_type = ConnectorType.GOOGLE_CONTACTS

        async def execute_api_call(
            self,
            client: GooglePeopleClient,
            **kwargs
        ) -> dict[str, Any]:
            # Only implement business logic
            return await client.search_contacts(kwargs["query"])

Data Registry Mode Example:
    class SearchContactsTool(ToolOutputMixin, ConnectorTool):
        registry_enabled = True  # Enable Data Registry mode

        async def execute_api_call(self, client, user_id, **kwargs):
            return await client.search_contacts(kwargs["query"])

        def format_registry_response(self, result: dict) -> UnifiedToolOutput:
            return self.build_contacts_output(
                contacts=result["contacts"],
                query=result.get("query"),
            )

Benefits:
- Reduces tool code from ~150 lines to ~30 lines (80% reduction)
- Eliminates 240 lines of DI boilerplate duplication
- Standardizes error handling across all tools
- Makes adding new connectors trivial (inherit + implement execute_api_call)
- Data Registry support via simple mixin + flag (no breaking changes)
"""

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime

from src.domains.agents.dependencies import ToolDependencies, get_dependencies
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    parse_user_id,
    validate_runtime_config,
)
from src.domains.connectors.models import CATEGORY_DISPLAY_NAMES, ConnectorType

if TYPE_CHECKING:
    from src.domains.agents.tools.output import StandardToolOutput

# Note: ToolResponse is deprecated in favor of UnifiedToolOutput (2025-12-29)

logger = structlog.get_logger(__name__)

# Type variable for API client type (GooglePeopleClient, GmailClient, etc.)
ClientType = TypeVar("ClientType")

# Type alias for tool output (Data Registry mode or legacy mode)
ToolOutputType = Union[str, "StandardToolOutput", UnifiedToolOutput]


class ConnectorTool[ClientType](ABC):
    """
    Abstract base class for connector-based tools.

    Provides common infrastructure for all tools that interact with external
    APIs through connectors (Google, Microsoft, etc.).

    Subclasses must implement:
    - connector_type: ConnectorType enum value
    - client_class: Type of API client to use
    - execute_api_call(): Business logic for API interaction

    Optional overrides:
    - create_client_factory(): Custom client instantiation logic
    - format_response(): Custom response formatting (legacy mode)
    - format_registry_response(): Data Registry response formatting (registry mode)
    - handle_error(): Custom error handling

    Data Registry Mode:
    - Set registry_enabled = True to return UnifiedToolOutput
    - Override format_registry_response() to build registry items
    - Use ToolOutputMixin for helper methods (build_contacts_output, etc.)

    Handles automatically:
    - Dependency injection (ToolDependencies pattern)
    - OAuth credentials retrieval
    - API client caching and reuse
    - Error handling and metrics tracking
    - User ID extraction and validation
    - Dual-mode output (str for legacy, UnifiedToolOutput for Data Registry)
    """

    # Subclasses must define these
    connector_type: ConnectorType
    client_class: type[ClientType]

    # Data Registry mode flag - set to True to enable registry output
    # When True, execute() returns UnifiedToolOutput instead of str
    registry_enabled: bool = False

    # API Key mode flag - set to True for connectors using global API key
    # When True, skips OAuth credentials check and uses simplified client factory
    uses_global_api_key: bool = False

    # Functional category for multi-provider support (email, calendar, contacts).
    # When set, the tool dynamically resolves the active provider at runtime
    # instead of using the hardcoded connector_type/client_class.
    # This enables transparent switching between Google and Apple providers.
    functional_category: str | None = None

    def __init__(self, tool_name: str, operation: str) -> None:
        """
        Initialize base tool.

        Args:
            tool_name: Tool identifier (e.g., "search_contacts_tool")
            operation: Operation name for metrics (e.g., "search", "list")
        """
        self.tool_name = tool_name
        self.operation = operation
        self.logger = logger.bind(tool=tool_name, operation=operation)
        # Runtime will be set in execute() - needed for user preferences lookup
        self.runtime: ToolRuntime | None = None

    async def execute(
        self,
        runtime: ToolRuntime,
        **kwargs: Any,
    ) -> ToolOutputType:
        """
        Main execution entrypoint called by LangChain.

        Orchestrates the entire tool execution flow:
        1. Validate runtime config and extract user_id
        2. Get dependencies (injected or fallback)
        3. Retrieve connector credentials
        4. Get or create cached API client
        5. Execute API call (delegated to subclass)
        6. Format response (Data Registry mode or legacy mode)
        7. Handle errors with standardized error messages

        Args:
            runtime: ToolRuntime injected by LangChain
            **kwargs: Tool-specific parameters

        Returns:
            - If registry_enabled=True: UnifiedToolOutput with registry items
            - If registry_enabled=False: JSON string (legacy mode)
        """
        user_id_str = None
        # Store runtime on instance for use by execute_api_call() methods
        # that need to access user preferences (timezone, language, etc.)
        self.runtime = runtime

        try:
            # Step 1: Validate runtime config
            config = validate_runtime_config(runtime, self.tool_name)
            if isinstance(config, UnifiedToolOutput):
                return config  # Early return on validation error (UnifiedToolOutput)

            # Extract validated config
            user_id_str = config.user_id
            user_uuid = self._parse_user_id(user_id_str)

            self.logger.debug(
                "tool_execution_started",
                user_id=user_id_str,
                registry_enabled=self.registry_enabled,
                kwargs=kwargs,
            )

            # Step 2: Get dependencies (injected or fallback)
            using_injected_deps, deps = self._get_deps_or_fallback(runtime)

            if using_injected_deps and deps is not None:
                connector_service = await deps.get_connector_service()

                # Resolve effective connector type and client class
                # (local variables — tool instances are singletons shared across requests)
                effective_connector_type = self.connector_type
                effective_client_class = self.client_class

                if self.functional_category:
                    from src.domains.connectors.clients.registry import ClientRegistry
                    from src.domains.connectors.provider_resolver import (
                        resolve_active_connector,
                    )

                    resolved_type = await resolve_active_connector(
                        user_uuid, self.functional_category, connector_service
                    )
                    if resolved_type is None:
                        return self._format_category_not_activated_error(self.functional_category)
                    effective_connector_type = resolved_type
                    resolved_class = ClientRegistry.get_client_class(resolved_type)
                    if resolved_class is not None:
                        effective_client_class = resolved_class

                if self.uses_global_api_key:
                    # Step 3 (API Key mode): Verify connector is enabled (no OAuth credentials)
                    if not await connector_service.is_connector_active(
                        user_uuid, effective_connector_type
                    ):
                        return self._format_connector_not_activated_error()

                    # Step 4 (API Key mode): Create client without credentials
                    client_factory = self.create_api_key_client_factory(user_uuid)
                else:
                    # Step 3: Get connector credentials (OAuth, Apple, or Hue)
                    if effective_connector_type.is_apple:
                        credentials = await connector_service.get_apple_credentials(
                            user_uuid, effective_connector_type
                        )
                    elif effective_connector_type.is_hue:
                        credentials = await connector_service.get_hue_credentials(user_uuid)
                    else:
                        credentials = await connector_service.get_connector_credentials(
                            user_uuid, effective_connector_type
                        )

                    if credentials is None:
                        return self._format_connector_not_activated_error()

                    # Step 4: Get or create cached API client
                    _effective_class = effective_client_class
                    _user = user_uuid
                    _creds = credentials
                    _svc = connector_service

                    async def _create_client():
                        return _effective_class(_user, _creds, _svc)

                    client_factory = _create_client

                client = await deps.get_or_create_client(
                    effective_client_class,
                    cache_key=(user_uuid, effective_connector_type),
                    factory=client_factory,
                )

                # Step 5: Execute API call (subclass-specific logic)
                result = await self.execute_api_call(client, user_uuid, **kwargs)

                # Step 6: Format response (Data Registry or legacy mode)
                if self.registry_enabled:
                    return self.format_registry_response(result)
                else:
                    return self.format_response(result)
            else:
                # Fallback path not implemented (requires session management)
                return self._format_error(
                    "tool_dependencies_required",
                    "Tool dependencies not injected. This tool requires ToolDependencies.",
                )

        except Exception as e:
            # Step 7: Handle errors
            return self.handle_error(e, user_id_str, kwargs)

    @abstractmethod
    async def execute_api_call(
        self,
        client: ClientType,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute the actual API call.

        This is the only method subclasses MUST implement.
        Contains only business logic specific to the tool.

        Args:
            client: API client instance (GooglePeopleClient, etc.)
            user_id: User UUID
            **kwargs: Tool-specific parameters

        Returns:
            Dict with API results (will be passed to format_response)

        Example:
            async def execute_api_call(self, client, user_id, **kwargs):
                query = kwargs["query"]
                max_results = kwargs.get("max_results", 10)
                return await client.search_contacts(query, max_results)
        """
        pass

    def create_client_factory(
        self,
        user_uuid: UUID,
        credentials: dict[str, Any],
        connector_service: Any,
    ) -> Any:
        """
        Create an async factory for API client instantiation (OAuth mode).

        Override this if your client requires custom initialization logic.

        Args:
            user_uuid: User UUID
            credentials: OAuth credentials dict
            connector_service: ConnectorService instance

        Returns:
            Async callable that creates API client
        """

        async def create_client() -> ClientType:
            return self.client_class(user_uuid, credentials, connector_service)

        return create_client

    def create_api_key_client_factory(self, user_uuid: UUID) -> Any:
        """
        Create an async factory for API Key client instantiation.

        Used when uses_global_api_key=True. The client uses a global API key
        from settings instead of per-user OAuth credentials.

        Override this if your API Key client requires custom initialization.

        Args:
            user_uuid: User UUID (for caching and logging)

        Returns:
            Async callable that creates API client
        """

        async def create_client() -> ClientType:
            return self.client_class(user_uuid)

        return create_client

    def format_response(self, result: dict[str, Any]) -> str:
        """
        Format API result as JSON string (legacy mode).

        Override this for custom formatting logic.

        Args:
            result: Dict returned by execute_api_call

        Returns:
            JSON string for LLM consumption
        """
        return json.dumps(result, ensure_ascii=False)

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format API result as UnifiedToolOutput (Data Registry mode).

        Override this when registry_enabled=True to build registry items.
        Default implementation raises NotImplementedError.

        Use ToolOutputMixin helper methods:
        - build_contacts_output() for contacts
        - build_emails_output() for emails
        - build_standard_output() for generic items

        Args:
            result: Dict returned by execute_api_call

        Returns:
            UnifiedToolOutput with message and registry_updates

        Raises:
            NotImplementedError: If registry_enabled=True but not overridden

        Example:
            def format_registry_response(self, result: dict) -> UnifiedToolOutput:
                return self.build_contacts_output(
                    contacts=result["contacts"],
                    query=result.get("query"),
                )
        """
        raise NotImplementedError(
            f"Tool '{self.tool_name}' has registry_enabled=True but format_registry_response() "
            "is not implemented. Override this method or use ToolOutputMixin."
        )

    def handle_error(
        self,
        error: Exception,
        user_id_str: str | None,
        params: dict[str, Any],
    ) -> str:
        """
        Handle tool execution errors.

        Override this for custom error handling logic.

        Args:
            error: Exception that occurred
            user_id_str: User ID string (may be None if error during validation)
            params: Tool parameters

        Returns:
            JSON string with error details
        """
        self.logger.error(
            "tool_execution_error",
            user_id=user_id_str,
            error=str(error),
            error_type=type(error).__name__,
            params=params,
        )

        # Use standardized error handler
        return handle_tool_exception(error, self.tool_name, params).model_dump_json()

    def _get_deps_or_fallback(self, runtime: ToolRuntime) -> tuple[bool, ToolDependencies | None]:
        """
        Try to get injected dependencies, fallback to None if not available.

        Returns:
            Tuple of (using_injected_deps: bool, deps: ToolDependencies | None)
        """
        try:
            deps = get_dependencies(runtime)
            self.logger.debug(
                "tool_using_injected_dependencies",
                db_session_id=id(deps.db),
            )
            return True, deps
        except RuntimeError:
            # Dependencies not injected - backward compatibility fallback
            self.logger.debug("tool_using_fallback_path")
            return False, None

    def _parse_user_id(self, user_id: str | UUID) -> UUID:
        """
        Parse user_id to UUID.

        Handles UUID objects, UUID strings, and ULIDs.

        Args:
            user_id: User ID as string or UUID

        Returns:
            UUID object

        Raises:
            ValueError: If user_id cannot be parsed
        """
        return parse_user_id(user_id)

    def _format_connector_not_activated_error(self) -> UnifiedToolOutput:
        """Format standard error for connector not activated."""
        return UnifiedToolOutput.failure(
            message=(
                f"Le service {self.connector_type.value} n'est pas activé. "
                "Rendez-vous dans Paramètres > Connecteurs pour l'activer."
            ),
            error_code="connector_not_activated",
        )

    def _format_category_not_activated_error(self, category: str) -> UnifiedToolOutput:
        """Format standard error when no provider is active for a functional category."""
        label = CATEGORY_DISPLAY_NAMES.get(category, category)
        return UnifiedToolOutput.failure(
            message=(
                f"Aucun service {label} n'est configuré. "
                "Rendez-vous dans Paramètres > Connecteurs pour activer "
                "un service Google, Apple ou Microsoft."
            ),
            error_code="category_not_activated",
        )

    def _format_error(self, error_code: str, message: str) -> UnifiedToolOutput:
        """Format standard error response."""
        return UnifiedToolOutput.failure(
            message=message,
            error_code=error_code,
        )

    async def get_user_preferences_safe(self) -> tuple[str, str]:
        """
        Get user timezone and locale with safe fallback to defaults.

        This helper eliminates the duplicate try-except pattern that appears
        in 25+ tool execute_api_call() methods for user preferences fetching.

        Returns:
            Tuple of (user_timezone, locale) with defaults ("UTC", "fr") on any error

        Example:
            >>> # In execute_api_call method:
            >>> user_timezone, locale = await self.get_user_preferences_safe()
            >>> # user_timezone and locale are guaranteed to have values
            >>> return {
            ...     "events": events,
            ...     "user_timezone": user_timezone,
            ...     "locale": locale,
            ... }

        Note:
            - Requires self.runtime to be set (done automatically in execute())
            - Falls back silently to defaults on any error
            - Uses get_user_preferences() from runtime_helpers
        """
        from src.core.constants import DEFAULT_LANGUAGE

        user_timezone = "UTC"
        locale = DEFAULT_LANGUAGE

        if self.runtime:
            try:
                from src.domains.agents.tools.runtime_helpers import get_user_preferences

                fetched_tz, _, fetched_locale = await get_user_preferences(self.runtime)
                user_timezone = fetched_tz
                locale = fetched_locale
            except Exception:
                # Silent fallback to defaults
                # Logging is already done in get_user_preferences()
                pass

        return user_timezone, locale


class APIKeyConnectorTool[ClientType](ABC):
    """
    Abstract base class for API key-based connector tools.

    Similar to ConnectorTool but for connectors that use API keys instead of OAuth.
    Handles automatic retrieval of user-specific API keys from the database.

    Subclasses must implement:
    - connector_type: ConnectorType enum value (e.g., OPENWEATHERMAP, PERPLEXITY)
    - client_class: Type of API client to use
    - execute_api_call(): Business logic for API interaction
    - create_client(): Factory method to create client from credentials

    Flow:
    1. Extract user_id from runtime config
    2. Retrieve API key credentials from database (ConnectorService.get_api_key_credentials)
    3. Create client instance with user's API key
    4. Execute API call
    5. Format response

    Example:
        class WeatherTool(APIKeyConnectorTool):
            connector_type = ConnectorType.OPENWEATHERMAP
            client_class = OpenWeatherMapClient

            def create_client(self, credentials: APIKeyCredentials) -> OpenWeatherMapClient:
                return OpenWeatherMapClient(api_key=credentials.api_key)

            async def execute_api_call(self, client: OpenWeatherMapClient, **kwargs):
                return await client.get_weather(kwargs["location"])
    """

    # Subclasses must define these
    connector_type: ConnectorType
    client_class: type[ClientType]

    # Data Registry mode flag - set to True to enable registry output
    registry_enabled: bool = False

    def __init__(self, tool_name: str, operation: str) -> None:
        """
        Initialize API key tool.

        Args:
            tool_name: Tool identifier (e.g., "get_weather_tool")
            operation: Operation name for metrics (e.g., "get_weather")
        """
        self.tool_name = tool_name
        self.operation = operation
        self.logger = logger.bind(tool=tool_name, operation=operation)

    async def execute(
        self,
        runtime: ToolRuntime,
        **kwargs: Any,
    ) -> ToolOutputType:
        """
        Main execution entrypoint called by LangChain.

        Orchestrates:
        1. Validate runtime config and extract user_id
        2. Get dependencies (injected)
        3. Retrieve API key credentials from database
        4. Create API client with user's key
        5. Execute API call
        6. Format response

        Args:
            runtime: ToolRuntime injected by LangChain
            **kwargs: Tool-specific parameters

        Returns:
            JSON string or UnifiedToolOutput depending on registry_enabled
        """
        user_id_str = None

        try:
            # Step 1: Validate runtime config
            config = validate_runtime_config(runtime, self.tool_name)
            if isinstance(config, UnifiedToolOutput):
                return config  # Early return on validation error (UnifiedToolOutput)

            user_id_str = config.user_id
            user_uuid = self._parse_user_id(user_id_str)

            self.logger.debug(
                "api_key_tool_execution_started",
                user_id=user_id_str,
                connector_type=self.connector_type.value,
                kwargs=kwargs,
            )

            # Step 2: Get dependencies
            using_injected_deps, deps = self._get_deps_or_fallback(runtime)

            if using_injected_deps and deps is not None:
                # Step 3: Get API key credentials from database
                connector_service = await deps.get_connector_service()
                credentials = await connector_service.get_api_key_credentials(
                    user_uuid, self.connector_type
                )

                if credentials is None:
                    return self._format_connector_not_activated_error()

                # Step 4: Create API client with user's key
                client = self.create_client(credentials, user_uuid)

                # Step 5: Execute API call (pass runtime for location resolution, etc.)
                result = await self.execute_api_call(client, user_uuid, runtime=runtime, **kwargs)

                # Step 6: Format response
                if self.registry_enabled:
                    return self.format_registry_response(result)
                else:
                    return self.format_response(result)
            else:
                return self._format_error(
                    "tool_dependencies_required",
                    "Tool dependencies not injected. This tool requires ToolDependencies.",
                )

        except Exception as e:
            return self.handle_error(e, user_id_str, kwargs)

    @abstractmethod
    def create_client(
        self,
        credentials: Any,  # APIKeyCredentials
        user_id: UUID,
    ) -> ClientType:
        """
        Create API client instance from credentials.

        Args:
            credentials: APIKeyCredentials with api_key
            user_id: User UUID (for logging/metrics)

        Returns:
            Configured API client instance
        """
        pass

    @abstractmethod
    async def execute_api_call(
        self,
        client: ClientType,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute the actual API call.

        Args:
            client: API client instance
            user_id: User UUID
            **kwargs: Tool-specific parameters

        Returns:
            Dict with API results
        """
        pass

    def format_response(self, result: dict[str, Any]) -> str:
        """Format API result as JSON string."""
        return json.dumps(result, ensure_ascii=False)

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format API result as UnifiedToolOutput (Data Registry mode)."""
        raise NotImplementedError(
            f"Tool '{self.tool_name}' has registry_enabled=True but format_registry_response() "
            "is not implemented."
        )

    def handle_error(
        self,
        error: Exception,
        user_id_str: str | None,
        params: dict[str, Any],
    ) -> str:
        """Handle tool execution errors."""
        self.logger.error(
            "api_key_tool_execution_error",
            user_id=user_id_str,
            error=str(error),
            error_type=type(error).__name__,
            params=params,
        )
        return handle_tool_exception(error, self.tool_name, params).model_dump_json()

    def _get_deps_or_fallback(self, runtime: ToolRuntime) -> tuple[bool, "ToolDependencies | None"]:
        """Get injected dependencies."""
        try:
            deps = get_dependencies(runtime)
            return True, deps
        except RuntimeError:
            return False, None

    def _parse_user_id(self, user_id: str | UUID) -> UUID:
        """Parse user_id to UUID."""
        return parse_user_id(user_id)

    def _format_connector_not_activated_error(self) -> UnifiedToolOutput:
        """Format standard error for connector not activated."""
        # Map connector types to user-friendly names
        connector_names = {
            ConnectorType.OPENWEATHERMAP: "OpenWeatherMap (météo)",
            ConnectorType.PERPLEXITY: "Perplexity AI (recherche web)",
            ConnectorType.WIKIPEDIA: "Wikipedia",
        }
        name = connector_names.get(self.connector_type, self.connector_type.value)

        return UnifiedToolOutput.failure(
            message=(
                f"Le service {name} n'est pas activé. "
                "Rendez-vous dans Paramètres > Connecteurs pour l'activer avec votre clé API."
            ),
            error_code="connector_not_activated",
        )

    def _format_error(self, error_code: str, message: str) -> UnifiedToolOutput:
        """Format standard error response."""
        return UnifiedToolOutput.failure(
            message=message,
            error_code=error_code,
        )
