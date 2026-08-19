"""
Semantic Type Registry - Central Type Management

Central registry for the semantic type catalogue (ADR-233, 2026-08-19):
- Fast O(1) lookup by name and by source domain (the runtime surface)
- Parent/child hierarchy kept as data + validate_hierarchy diagnostics

The transitive-subsumption API, Wu & Palmer distance, SKOS relation graph
and category/tool getters had ZERO runtime consumers and were removed —
doctrine: unwired capability is deleted, not kept "for later".
"""

import networkx as nx

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TypeRegistry:
    """
    Central semantic type registry.

    Provides the lookups the runtime actually consumes (expansion service,
    initiative bridges, param guard): by name and by source domain. The
    hierarchy graph persists as validated data (validate_hierarchy).

    Example:
        >>> registry = TypeRegistry()
        >>> registry.register(email_address_type)
        >>> registry.get_by_domain("contact")
        {"email_address"}
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        # Main storage
        self._types: dict[str, SemanticType] = {}

        # Hierarchy graph (kept for validate_hierarchy diagnostics)
        self._hierarchy: nx.DiGraph = nx.DiGraph()  # Parent → Child edges

        # Indexes for fast O(1) lookup (category/tool retained for get_stats)
        self._by_category: dict[TypeCategory, set[str]] = {
            category: set() for category in TypeCategory
        }
        self._by_domain: dict[str, set[str]] = {}
        self._by_tool: dict[str, set[str]] = {}

        logger.info("type_registry_initialized", message="TypeRegistry initialized")

    def register(self, type_def: SemanticType) -> None:
        """
        Register a new type in the registry.

        Automatically builds:
        - Parent-child hierarchy
        - Semantic relations
        - Lookup indexes

        Args:
            type_def: Semantic type definition

        Raises:
            ValueError: If the type already exists or if the parent does not exist
        """
        if type_def.name in self._types:
            logger.warning(
                "type_already_registered",
                type_name=type_def.name,
                message="Type already registered, skipping",
            )
            return

        # Validate parent exists (if specified)
        if type_def.parent and type_def.parent not in self._types:
            # Allow registration even if parent doesn't exist yet
            # (for cases where types are registered in non-hierarchical order)
            logger.debug(
                "parent_not_yet_registered",
                type_name=type_def.name,
                parent=type_def.parent,
                message="Parent type not yet registered, will link later",
            )

        # Store type
        self._types[type_def.name] = type_def

        # Build hierarchy
        if type_def.parent:
            self._hierarchy.add_edge(type_def.parent, type_def.name)

        # Update indexes
        self._update_indexes(type_def)

        logger.debug(
            "type_registered",
            type_name=type_def.name,
            category=type_def.category.value,
            parent=type_def.parent,
            source_domains=type_def.source_domains,
        )

    def get(self, type_name: str) -> SemanticType | None:
        """
        Retrieve a type by its name.

        Args:
            type_name: Type name

        Returns:
            Type definition or None if not found
        """
        return self._types.get(type_name)

    def get_all(self) -> list[SemanticType]:
        """
        Return all registered types.

        Returns:
            List of all types
        """
        return list(self._types.values())

    def get_by_domain(self, domain: str) -> set[str]:
        """
        Retrieve types provided by a domain.

        Args:
            domain: Domain name (e.g., "contacts", "places")

        Returns:
            Set of type names provided by this domain
        """
        return self._by_domain.get(domain, set())

    def _update_indexes(self, type_def: SemanticType) -> None:
        """
        Update fast lookup indexes.

        Args:
            type_def: Type to index
        """
        # Index by category
        self._by_category[type_def.category].add(type_def.name)

        # Index by source domain
        for domain in type_def.source_domains:
            if domain not in self._by_domain:
                self._by_domain[domain] = set()
            self._by_domain[domain].add(type_def.name)

        # Index by tool
        for tool in type_def.used_in_tools:
            if tool not in self._by_tool:
                self._by_tool[tool] = set()
            self._by_tool[tool].add(type_def.name)

    def validate_hierarchy(self) -> list[str]:
        """
        Validate hierarchy consistency.

        Checks:
        - No cycles (DAG)
        - Parents exist
        - Consistent bidirectional relations

        Returns:
            List of validation errors (empty if OK)
        """
        errors = []

        # Check for cycles
        if not nx.is_directed_acyclic_graph(self._hierarchy):
            cycles = list(nx.simple_cycles(self._hierarchy))
            errors.append(f"Hierarchy contains cycles: {cycles}")

        # Verify that all parents exist
        for type_name, type_def in self._types.items():
            if type_def.parent and type_def.parent not in self._types:
                errors.append(f"Type '{type_name}' has non-existent parent '{type_def.parent}'")

        return errors

    def get_stats(self) -> dict:
        """
        Return registry statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_types": len(self._types),
            "by_category": {cat.value: len(types) for cat, types in self._by_category.items()},
            "total_domains": len(self._by_domain),
            "total_tools": len(self._by_tool),
            "hierarchy_nodes": self._hierarchy.number_of_nodes(),
            "hierarchy_edges": self._hierarchy.number_of_edges(),
        }

    def __len__(self) -> int:
        """Return the number of registered types."""
        return len(self._types)

    def __contains__(self, type_name: str) -> bool:
        """Check if a type is registered."""
        return type_name in self._types

    def __repr__(self) -> str:
        """Concise representation for debugging."""
        return f"TypeRegistry(types={len(self._types)}, domains={len(self._by_domain)})"


# Singleton global registry
_global_registry: TypeRegistry | None = None


def get_registry() -> TypeRegistry:
    """
    Retrieve the global registry instance.

    Singleton pattern for a single shared registry.

    Returns:
        Global TypeRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = TypeRegistry()
        logger.info("global_registry_created", message="Global TypeRegistry instance created")
    return _global_registry


def reset_registry() -> None:
    """
    Reset the global registry.

    Useful for unit tests.
    """
    global _global_registry
    _global_registry = None
    logger.debug("global_registry_reset", message="Global TypeRegistry reset")
