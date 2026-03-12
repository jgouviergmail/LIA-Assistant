"""
Tool Schema Registry - Single source of truth for tool response schemas.

This module provides a centralized, thread-safe registry for storing and accessing
JSON schemas that describe the response structure of all tools in the system.

Phase 2.1 - Schema Mismatch Resolution (Issue #32)

Responsibilities:
    - Store JSON Schema for each tool's response structure
    - Provide thread-safe access to schemas
    - Validate schemas on registration
    - Generate reference examples for planner

Architecture:
    - Singleton pattern with double-checked locking
    - Thread-safe operations using RLock
    - In-memory storage with dict indexing by tool_name

Usage:
    >>> registry = ToolSchemaRegistry.get_instance()
    >>> registry.register_schema("search_contacts_tool", schema, examples)
    >>> schema = registry.get_schema("search_contacts_tool")
    >>> tools = registry.list_tools()

Best Practices (2025):
    - Singleton for global access
    - Thread-safe for concurrent access
    - Structured logging for observability
    - Type hints for clarity

Author: Phase 2.1 Implementation
Created: 2025-11-23
"""

import threading
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ToolSchemaRegistry:
    """
    Thread-safe singleton registry for tool response schemas.

    This registry serves as the single source of truth for all tool response schemas,
    enabling dynamic injection into planner prompts and pre-execution validation.

    Attributes:
        _instance: Singleton instance (class-level)
        _schemas: Dict mapping tool_name -> schema data
        _lock: Reentrant lock for thread safety

    Thread Safety:
        All public methods are thread-safe using RLock.
        Double-checked locking pattern for singleton initialization.

    Examples:
        >>> # Get singleton instance
        >>> registry = ToolSchemaRegistry.get_instance()
        >>>
        >>> # Register a schema
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "contacts": {
        ...             "type": "array",
        ...             "items": {"type": "object"}
        ...         }
        ...     }
        ... }
        >>> examples = [
        ...     {
        ...         "description": "Get first contact's email",
        ...         "reference": "$steps.search.contacts[0].emailAddresses[0].value",
        ...         "expected_type": "string"
        ...     }
        ... ]
        >>> registry.register_schema("search_contacts_tool", schema, examples)
        >>>
        >>> # Retrieve schema
        >>> retrieved = registry.get_schema("search_contacts_tool")
        >>> assert retrieved["response_schema"] == schema
        >>>
        >>> # List all registered tools
        >>> tools = registry.list_tools()
        >>> assert "search_contacts_tool" in tools
    """

    # Class-level singleton instance
    _instance: "ToolSchemaRegistry | None" = None

    # Schema storage: {tool_name: {response_schema, examples, registered_at}}
    _schemas: dict[str, dict[str, Any]] = {}

    # Thread safety lock (reentrant to allow nested locks)
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ToolSchemaRegistry":
        """
        Get or create singleton instance (thread-safe with double-checked locking).

        Uses double-checked locking pattern to minimize lock contention:
        1. Check if instance exists (no lock)
        2. If not, acquire lock
        3. Check again after acquiring lock (prevent race condition)
        4. Create instance if still None

        Returns:
            Singleton ToolSchemaRegistry instance

        Thread Safety:
            Safe for concurrent access from multiple threads.
            First caller creates instance, subsequent callers get same instance.

        Examples:
            >>> r1 = ToolSchemaRegistry.get_instance()
            >>> r2 = ToolSchemaRegistry.get_instance()
            >>> assert r1 is r2  # Same instance
        """
        # First check (no lock) - fast path for already initialized
        if cls._instance is None:
            # Acquire lock for initialization
            with cls._lock:
                # Double-check after acquiring lock (prevent race condition)
                if cls._instance is None:
                    cls._instance = cls()
                    logger.info(
                        "schema_registry_initialized",
                        schemas_count=0,
                        message="Tool Schema Registry singleton created",
                    )

        return cls._instance

    def register_schema(
        self,
        tool_name: str,
        schema: dict[str, Any],
        examples: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Register tool response schema.

        Stores the JSON schema describing the response structure of a tool,
        along with optional reference examples for documentation.

        Args:
            tool_name: Tool name (e.g., "search_contacts_tool")
                Must be unique. Registering same tool_name twice will overwrite.
            schema: JSON Schema dict describing tool response structure
                Must be valid JSON Schema (type, properties, etc.)
            examples: Optional list of reference examples
                Each example should have: description, reference, expected_type

        Thread Safety:
            Thread-safe. Multiple threads can register schemas concurrently.

        Validation:
            - Validates tool_name is non-empty string
            - Validates schema is non-empty dict
            - Logs warning if overwriting existing schema

        Examples:
            >>> registry = ToolSchemaRegistry.get_instance()
            >>>
            >>> # Register with examples
            >>> registry.register_schema(
            ...     "get_contact_details_tool",
            ...     {
            ...         "type": "object",
            ...         "properties": {
            ...             "contacts": {
            ...                 "type": "array",
            ...                 "items": {
            ...                     "type": "object",
            ...                     "properties": {
            ...                         "emailAddresses": {
            ...                             "type": "array",
            ...                             "items": {
            ...                                 "type": "object",
            ...                                 "properties": {
            ...                                     "value": {"type": "string"}
            ...                                 }
            ...                             }
            ...                         }
            ...                     }
            ...                 }
            ...             }
            ...         }
            ...     },
            ...     examples=[
            ...         {
            ...             "description": "Get first contact's first email",
            ...             "reference": "$steps.details.contacts[0].emailAddresses[0].value",
            ...             "expected_type": "string"
            ...         }
            ...     ]
            ... )
        """
        # Input validation
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError(f"tool_name must be non-empty string, got: {tool_name!r}")

        if not schema or not isinstance(schema, dict):
            raise ValueError(f"schema must be non-empty dict, got: {schema!r}")

        # Normalize examples
        if examples is None:
            examples = []

        # Thread-safe registration
        with self._lock:
            # Check if overwriting existing schema
            if tool_name in self._schemas:
                logger.warning(
                    "schema_overwrite",
                    tool_name=tool_name,
                    message="Overwriting existing schema registration",
                )

            # Store schema with metadata
            self._schemas[tool_name] = {
                "response_schema": schema,
                "examples": examples,
                "registered_at": datetime.utcnow().isoformat(),
            }

            # Count fields in schema
            fields_count = len(schema.get("properties", {}))
            examples_count = len(examples)

            logger.info(
                "schema_registered",
                tool_name=tool_name,
                fields_count=fields_count,
                examples_count=examples_count,
                message=f"Registered schema for {tool_name} with {fields_count} fields",
            )

    def get_schema(self, tool_name: str) -> dict[str, Any] | None:
        """
        Get schema for tool (thread-safe).

        Retrieves the complete schema registration for a tool, including
        response_schema, examples, and registration timestamp.

        Args:
            tool_name: Tool name to lookup

        Returns:
            Dict with keys: response_schema, examples, registered_at
            None if tool not registered

        Thread Safety:
            Thread-safe read operation. No lock needed for dict.get().

        Examples:
            >>> registry = ToolSchemaRegistry.get_instance()
            >>> schema_data = registry.get_schema("search_contacts_tool")
            >>>
            >>> if schema_data:
            ...     response_schema = schema_data["response_schema"]
            ...     examples = schema_data["examples"]
            ...     registered_at = schema_data["registered_at"]
            ... else:
            ...     print("Schema not found")
        """
        # Note: dict.get() is thread-safe for read operations in CPython
        # due to GIL (Global Interpreter Lock)
        return self._schemas.get(tool_name)

    def list_tools(self) -> list[str]:
        """
        List all tools with registered schemas (sorted alphabetically).

        Returns:
            Sorted list of tool names

        Thread Safety:
            Thread-safe. Returns snapshot of current tool names.

        Examples:
            >>> registry = ToolSchemaRegistry.get_instance()
            >>> tools = registry.list_tools()
            >>> print(f"Registered tools: {', '.join(tools)}")
            Registered tools: get_contact_details_tool, list_contacts_tool, search_contacts_tool
        """
        # Thread-safe: list() creates snapshot, sorted() operates on snapshot
        return sorted(self._schemas.keys())

    def has_schema(self, tool_name: str) -> bool:
        """
        Check if tool has registered schema.

        Args:
            tool_name: Tool name to check

        Returns:
            True if schema registered, False otherwise

        Thread Safety:
            Thread-safe read operation.

        Examples:
            >>> registry = ToolSchemaRegistry.get_instance()
            >>> if registry.has_schema("search_contacts_tool"):
            ...     schema = registry.get_schema("search_contacts_tool")
            ... else:
            ...     print("Schema not registered")
        """
        return tool_name in self._schemas

    def clear(self) -> None:
        """
        Clear all schemas (for testing only).

        WARNING: This should only be used in tests. In production, schemas
        are registered once at startup and never cleared.

        Thread Safety:
            Thread-safe. Acquires lock before clearing.

        Examples:
            >>> # In tests
            >>> registry = ToolSchemaRegistry.get_instance()
            >>> registry.clear()
            >>> assert len(registry.list_tools()) == 0
        """
        with self._lock:
            count = len(self._schemas)
            self._schemas.clear()

            logger.info(
                "schema_registry_cleared",
                cleared_count=count,
                message=f"Cleared {count} schemas from registry (testing only)",
            )

    def get_stats(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dict with statistics:
                - total_tools: Total number of registered tools
                - tools_with_examples: Number of tools with examples
                - total_examples: Total number of examples across all tools

        Thread Safety:
            Thread-safe. Computes stats on snapshot.

        Examples:
            >>> registry = ToolSchemaRegistry.get_instance()
            >>> stats = registry.get_stats()
            >>> print(f"Registered {stats['total_tools']} tools")
            >>> print(f"{stats['tools_with_examples']} have examples")
            >>> print(f"{stats['total_examples']} total examples")
        """
        with self._lock:
            total_tools = len(self._schemas)
            tools_with_examples = sum(
                1 for schema_data in self._schemas.values() if schema_data["examples"]
            )
            total_examples = sum(
                len(schema_data["examples"]) for schema_data in self._schemas.values()
            )

            return {
                "total_tools": total_tools,
                "tools_with_examples": tools_with_examples,
                "total_examples": total_examples,
            }
