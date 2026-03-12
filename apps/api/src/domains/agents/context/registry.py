"""
Context Type Registry for dynamic context type discovery.

Provides a centralized registry pattern for auto-discovering and validating
context types across all agents. Enables 100% generic context management.

Architecture:
    - ContextTypeDefinition: Pydantic model defining context structure
    - ContextTypeRegistry: Singleton registry with auto-discovery
    - Type-safe validation via Pydantic

Example:
    # In google_contacts_tools.py
    ContextTypeRegistry.register(
        ContextTypeDefinition(
            context_type="contacts",
            agent_name="contacts_agent",
            item_schema=ContactItem,
            primary_id_field="resource_name",
            display_name_field="name",
            reference_fields=["name", "emails", "phones"]
        )
    )

    # In gmail_tools.py (future)
    ContextTypeRegistry.register(
        ContextTypeDefinition(
            context_type="emails",
            agent_name="emails_agent",
            item_schema=EmailItem,
            primary_id_field="message_id",
            display_name_field="subject",
            reference_fields=["subject", "from", "to"]
        )
    )
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ContextTypeDefinition(BaseModel):
    """
    Complete definition of a context type.

    Enables auto-configuration of the context system for any data entity
    (contacts, emails, calendar events, etc.).

    Attributes:
        domain: Primary domain identifier ("contacts", "emails", "events").
        context_type: Legacy alias for domain (maintained for V1 compatibility).
        agent_name: Name of the agent owning this context ("contacts_agent").
        item_schema: Pydantic model for type-safe items (ContactItem, EmailItem).
        primary_id_field: Field name for unique ID ("resource_name", "message_id").
        display_name_field: Field for human-readable display ("name", "subject").
        reference_fields: Fields searchable for fuzzy matching (["name", "emails"]).
        icon: Optional emoji/icon for UI display.

    Example:
        >>> ContactsContext = ContextTypeDefinition(
        ...     domain="contacts",
        ...     agent_name="contacts_agent",
        ...     item_schema=ContactItem,
        ...     primary_id_field="resource_name",
        ...     display_name_field="name",
        ...     reference_fields=["name", "emails", "phones"],
        ...     icon="📇"
        ... )

    Note:
        domain is the primary key. context_type is auto-set to match domain
        for backward compatibility with V1 code.
    """

    domain: str = Field(
        description="Primary domain identifier (e.g., 'contacts', 'emails', 'events')"
    )
    context_type: str | None = Field(
        default=None,
        description="Legacy alias for domain (auto-set if not provided, for V1 compatibility)",
    )
    agent_name: str = Field(description="Agent owning this context (e.g., 'contacts_agent')")
    item_schema: type[BaseModel] | None = Field(
        default=None, description="Pydantic model for type-safe items (optional)"
    )
    primary_id_field: str = Field(
        description="Field name for unique item ID (e.g., 'resource_name')"
    )
    display_name_field: str = Field(
        description="Field for human-readable display (e.g., 'name', 'subject')"
    )
    reference_fields: list[str] = Field(
        description="Fields searchable for fuzzy matching (e.g., ['name', 'emails'])"
    )
    icon: str | None = Field(default=None, description="Optional emoji/icon for UI")

    def model_post_init(self, __context: Any) -> None:
        """Auto-set context_type to match domain if not explicitly provided."""
        if self.context_type is None:
            self.context_type = self.domain

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain is lowercase and alphanumeric."""
        if not v.islower() or not v.replace("_", "").isalnum():
            raise ValueError(f"domain must be lowercase alphanumeric with underscores: {v}")
        return v

    @field_validator("reference_fields")
    @classmethod
    def validate_reference_fields(cls, v: list[str]) -> list[str]:
        """Ensure at least one reference field exists."""
        if not v:
            raise ValueError("reference_fields must contain at least one field")
        return v

    model_config = {"arbitrary_types_allowed": True}  # Allow Type[BaseModel]


class ContextTypeRegistry:
    """
    Singleton registry for context type auto-discovery.

    Provides centralized registration and retrieval of context types.
    Thread-safe, module-level singleton pattern.

    Usage:
        # Register (typically in tool module __init__ or at import)
        ContextTypeRegistry.register(definition)

        # Get definition
        definition = ContextTypeRegistry.get_definition("contacts")

        # List all registered types
        types = ContextTypeRegistry.list_all()

    Best Practices:
        - Register context types at module import time
        - One context type per data entity
        - Use descriptive context_type names
        - Keep reference_fields focused (3-5 fields max)
    """

    _registry: dict[str, ContextTypeDefinition] = {}

    @classmethod
    def register(cls, definition: ContextTypeDefinition) -> None:
        """
        Register a context type definition.

        Args:
            definition: ContextTypeDefinition to register.

        Raises:
            ValueError: If definition validation fails.

        Note:
            If context_type already exists, logs warning and overwrites.
            This is intentional for hot-reload scenarios during development.
        """
        if definition.context_type in cls._registry:
            logger.warning(
                "context_type_already_registered_overwriting",
                context_type=definition.context_type,
                agent_name=definition.agent_name,
            )

        cls._registry[definition.context_type] = definition

        logger.info(
            "context_type_registered",
            context_type=definition.context_type,
            agent_name=definition.agent_name,
            reference_fields=definition.reference_fields,
        )

    @classmethod
    def get_definition(cls, context_type: str) -> ContextTypeDefinition:
        """
        Retrieve a registered context type definition.

        Args:
            context_type: Context type identifier.

        Returns:
            ContextTypeDefinition for the requested type.

        Raises:
            ValueError: If context_type not registered.

        Example:
            >>> definition = ContextTypeRegistry.get_definition("contacts")
            >>> print(definition.agent_name)  # "contacts_agent"
        """
        if context_type not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Context type '{context_type}' not registered. "
                f"Available types: {available if available else 'none'}"
            )

        return cls._registry[context_type]

    @classmethod
    def list_all(cls) -> list[str]:
        """
        List all registered context types.

        Returns:
            List of context type identifiers.

        Example:
            >>> ContextTypeRegistry.list_all()
            ['contacts', 'emails', 'events']
        """
        return list(cls._registry.keys())

    @classmethod
    def get_by_agent(cls, agent_name: str) -> list[ContextTypeDefinition]:
        """
        Get all context types for a specific agent.

        Args:
            agent_name: Name of the agent.

        Returns:
            List of ContextTypeDefinitions owned by this agent.

        Example:
            >>> definitions = ContextTypeRegistry.get_by_agent("contacts_agent")
            >>> # [ContextTypeDefinition(domain="contacts", ...)]
        """
        return [
            definition
            for definition in cls._registry.values()
            if definition.agent_name == agent_name
        ]

    @classmethod
    def get_by_domain(cls, domain: str) -> ContextTypeDefinition:
        """
        Retrieve a registered context type definition by domain.

        This is an alias for get_definition() but uses domain terminology
        for clarity in the new architecture.

        Args:
            domain: Domain identifier ("contacts", "emails", "events").

        Returns:
            ContextTypeDefinition for the requested domain.

        Raises:
            ValueError: If domain not registered.

        Example:
            >>> definition = ContextTypeRegistry.get_by_domain("contacts")
            >>> print(definition.agent_name)  # "contacts_agent"
        """
        return cls.get_definition(domain)

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered context types.

        WARNING: Only use in tests to reset registry state.
        Production code should never call this method.
        """
        cls._registry.clear()
        logger.warning("context_registry_cleared")
