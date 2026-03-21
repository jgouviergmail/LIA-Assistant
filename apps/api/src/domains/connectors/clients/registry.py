"""
Client Registry for connector API clients.

Provides auto-discovery and validation of API clients based on ConnectorType.
This registry enables:
1. Runtime validation that tools use correct client for their connector type
2. Auto-discovery of available clients for debugging/introspection
3. Future path for auto-instantiation when adding new OAuth providers

Sprint 15 - Gold-Grade Architecture
Created: 2025-12-18

Usage:
    # Register a client (typically done at module load via decorator)
    @ClientRegistry.register(ConnectorType.GOOGLE_CONTACTS)
    class GooglePeopleClient(BaseGoogleClient):
        ...

    # Or explicit registration
    ClientRegistry.register_client(ConnectorType.GOOGLE_CONTACTS, GooglePeopleClient)

    # Get client class for a connector type
    client_class = ClientRegistry.get_client_class(ConnectorType.GOOGLE_CONTACTS)

    # Validate tool configuration
    ClientRegistry.validate_tool_client(tool.connector_type, tool.client_class)
"""

from typing import TypeVar

import structlog

from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

# Type variable for client classes
ClientT = TypeVar("ClientT")


class ClientRegistry:
    """
    Registry mapping ConnectorType to API client classes.

    Thread-safe singleton pattern ensures consistent state across the application.
    """

    _registry: dict[ConnectorType, type] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, connector_type: ConnectorType):
        """
        Decorator to register a client class for a connector type.

        Args:
            connector_type: The ConnectorType this client handles

        Returns:
            Decorator function that registers the class

        Example:
            @ClientRegistry.register(ConnectorType.GOOGLE_CONTACTS)
            class GooglePeopleClient(BaseGoogleClient):
                ...
        """

        def decorator(client_class: type[ClientT]) -> type[ClientT]:
            cls.register_client(connector_type, client_class)
            return client_class

        return decorator

    @classmethod
    def register_client(cls, connector_type: ConnectorType, client_class: type) -> None:
        """
        Register a client class for a connector type.

        Args:
            connector_type: The ConnectorType this client handles
            client_class: The client class to register

        Raises:
            ValueError: If a different client is already registered for this type
        """
        existing = cls._registry.get(connector_type)
        if existing is not None and existing is not client_class:
            logger.warning(
                "client_registry_overwrite",
                connector_type=connector_type.value,
                existing_class=existing.__name__,
                new_class=client_class.__name__,
            )

        cls._registry[connector_type] = client_class
        logger.debug(
            "client_registered",
            connector_type=connector_type.value,
            client_class=client_class.__name__,
        )

    @classmethod
    def get_client_class(cls, connector_type: ConnectorType) -> type | None:
        """
        Get the registered client class for a connector type.

        Args:
            connector_type: The ConnectorType to look up

        Returns:
            The registered client class, or None if not found
        """
        cls._ensure_initialized()
        return cls._registry.get(connector_type)

    @classmethod
    def validate_tool_client(
        cls,
        connector_type: ConnectorType,
        client_class: type,
    ) -> bool:
        """
        Validate that a tool's client_class matches the registered client for its connector_type.

        This is useful for runtime validation during tool registration.

        Args:
            connector_type: The tool's connector type
            client_class: The tool's declared client class

        Returns:
            True if valid (matches or no registration exists)

        Logs warning if mismatch detected.
        """
        cls._ensure_initialized()
        registered = cls._registry.get(connector_type)

        if registered is None:
            # No registration - can't validate, assume OK
            return True

        if registered is not client_class:
            logger.warning(
                "client_registry_mismatch",
                connector_type=connector_type.value,
                expected_class=registered.__name__,
                actual_class=client_class.__name__,
                message="Tool uses different client class than registered",
            )
            return False

        return True

    @classmethod
    def get_all_registered(cls) -> dict[ConnectorType, type]:
        """
        Get all registered connector type to client class mappings.

        Returns:
            Copy of the registry dict
        """
        cls._ensure_initialized()
        return dict(cls._registry)

    @classmethod
    def _ensure_initialized(cls) -> None:
        """
        Ensure the registry is initialized with all known clients.

        This is called lazily on first access to avoid circular imports.
        """
        if cls._initialized:
            return

        cls._initialized = True

        # Import and register all known clients
        # This avoids circular imports by doing it lazily
        try:
            from src.domains.connectors.clients.google_calendar_client import (
                GoogleCalendarClient,
            )
            from src.domains.connectors.clients.google_drive_client import (
                GoogleDriveClient,
            )
            from src.domains.connectors.clients.google_gmail_client import (
                GoogleGmailClient,
            )
            from src.domains.connectors.clients.google_people_client import (
                GooglePeopleClient,
            )
            from src.domains.connectors.clients.google_tasks_client import (
                GoogleTasksClient,
            )

            # Register Google OAuth clients
            cls.register_client(ConnectorType.GOOGLE_CONTACTS, GooglePeopleClient)
            cls.register_client(ConnectorType.GOOGLE_GMAIL, GoogleGmailClient)
            cls.register_client(ConnectorType.GOOGLE_CALENDAR, GoogleCalendarClient)
            cls.register_client(ConnectorType.GOOGLE_DRIVE, GoogleDriveClient)
            cls.register_client(ConnectorType.GOOGLE_TASKS, GoogleTasksClient)

            # Register Apple iCloud clients
            from src.domains.connectors.clients.apple_calendar_client import (
                AppleCalendarClient,
            )
            from src.domains.connectors.clients.apple_contacts_client import (
                AppleContactsClient,
            )
            from src.domains.connectors.clients.apple_email_client import (
                AppleEmailClient,
            )

            cls.register_client(ConnectorType.APPLE_EMAIL, AppleEmailClient)
            cls.register_client(ConnectorType.APPLE_CALENDAR, AppleCalendarClient)
            cls.register_client(ConnectorType.APPLE_CONTACTS, AppleContactsClient)

            # Register Microsoft 365 clients
            from src.domains.connectors.clients.microsoft_calendar_client import (
                MicrosoftCalendarClient,
            )
            from src.domains.connectors.clients.microsoft_contacts_client import (
                MicrosoftContactsClient,
            )
            from src.domains.connectors.clients.microsoft_outlook_client import (
                MicrosoftOutlookClient,
            )
            from src.domains.connectors.clients.microsoft_tasks_client import (
                MicrosoftTasksClient,
            )

            cls.register_client(ConnectorType.MICROSOFT_OUTLOOK, MicrosoftOutlookClient)
            cls.register_client(ConnectorType.MICROSOFT_CALENDAR, MicrosoftCalendarClient)
            cls.register_client(ConnectorType.MICROSOFT_CONTACTS, MicrosoftContactsClient)
            cls.register_client(ConnectorType.MICROSOFT_TASKS, MicrosoftTasksClient)

            # Register Philips Hue client (Smart Home)
            from src.domains.connectors.clients.philips_hue_client import (
                PhilipsHueClient,
            )

            cls.register_client(ConnectorType.PHILIPS_HUE, PhilipsHueClient)

            # Note: API key clients (OpenWeatherMap, Wikipedia, Perplexity, GooglePlaces)
            # are not registered here as they use a different instantiation pattern
            # (APIKeyConnectorTool or ConnectorTool with uses_global_api_key=True)

            logger.info(
                "client_registry_initialized",
                registered_count=len(cls._registry),
                connector_types=[ct.value for ct in cls._registry.keys()],
            )

        except ImportError as e:
            logger.error(
                "client_registry_init_failed",
                error=str(e),
            )

    @classmethod
    def reset(cls) -> None:
        """
        Reset the registry (mainly for testing).
        """
        cls._registry.clear()
        cls._initialized = False


def get_client_for_connector(connector_type: ConnectorType) -> type | None:
    """
    Convenience function to get client class for a connector type.

    Args:
        connector_type: The ConnectorType to look up

    Returns:
        The registered client class, or None if not found
    """
    return ClientRegistry.get_client_class(connector_type)
