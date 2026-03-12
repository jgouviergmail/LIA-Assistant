"""
Semantic Type Registry - Central Type Management

Central registry for managing 96+ semantic types with:
- Type hierarchy (DAG - Directed Acyclic Graph)
- Semantic relations (RDF-style)
- Fast O(1) lookup by name, category, domain, tool
- Wu & Palmer semantic distance computation

Uses NetworkX for efficient graph management.
"""

import networkx as nx

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TypeRegistry:
    """
    Central semantic type registry.

    Manages hierarchy, relations, and provides fast lookups
    to support semantic expansion and reasoning.

    Features:
    - Type hierarchy (DAG with NetworkX)
    - Semantic relations (related, broader, narrower)
    - Fast O(1) lookup by name, category, domain, tool
    - Wu & Palmer semantic distance computation
    - Subsumption validation (is-a)

    Example:
        >>> registry = TypeRegistry()
        >>> registry.register(email_address_type)
        >>> registry.register(physical_address_type)
        >>> registry.is_subtype_of("physical_address", "PostalAddress")
        True
        >>> registry.compute_distance_wu_palmer("email_address", "phone_number")
        0.67  # Both are ContactPoint subtypes
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        # Main storage
        self._types: dict[str, SemanticType] = {}

        # Graphs for hierarchy and relations
        self._hierarchy: nx.DiGraph = nx.DiGraph()  # Parent → Child edges
        self._relations: nx.MultiDiGraph = nx.MultiDiGraph()  # Semantic relations

        # Indexes for fast O(1) lookup
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

        # Build semantic relations
        for related in type_def.related_types:
            self._relations.add_edge(type_def.name, related, relation="related")

        for broader in type_def.broader_types:
            self._relations.add_edge(type_def.name, broader, relation="broader")

        for narrower in type_def.narrower_types:
            self._relations.add_edge(type_def.name, narrower, relation="narrower")

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

    def get_by_category(self, category: TypeCategory) -> set[str]:
        """
        Retrieve type names for a category.

        Args:
            category: Type category

        Returns:
            Set of type names
        """
        return self._by_category.get(category, set())

    def get_by_domain(self, domain: str) -> set[str]:
        """
        Retrieve types provided by a domain.

        Args:
            domain: Domain name (e.g., "contacts", "places")

        Returns:
            Set of type names provided by this domain
        """
        return self._by_domain.get(domain, set())

    def get_by_tool(self, tool_name: str) -> set[str]:
        """
        Retrieve types used by a tool.

        Args:
            tool_name: Tool name

        Returns:
            Set of type names used by this tool
        """
        return self._by_tool.get(tool_name, set())

    def get_hierarchy_path(self, type_name: str) -> list[str]:
        """
        Return the complete hierarchy path (root -> type).

        Args:
            type_name: Type name

        Returns:
            Path from root to type (list of names)

        Example:
            >>> registry.get_hierarchy_path("physical_address")
            ["Thing", "Place", "PostalAddress", "physical_address"]
        """
        if type_name not in self._hierarchy:
            # Type without parent (root or not registered)
            return [type_name]

        # Find all ancestors
        ancestors = list(nx.ancestors(self._hierarchy, type_name))
        if not ancestors:
            return [type_name]

        # Find the root (node without predecessors)
        roots = [n for n in ancestors if self._hierarchy.in_degree(n) == 0]
        if not roots:
            # No root found, return just the type
            return [type_name]

        # Take the first root (should normally be unique)
        root = roots[0]

        # Find the shortest path from root to type
        try:
            path = nx.shortest_path(self._hierarchy, root, type_name)
            return path  # type: ignore[no-any-return]
        except nx.NetworkXNoPath:
            return [type_name]

    def get_subtypes(self, type_name: str, recursive: bool = True) -> set[str]:
        """
        Return subtypes (descendants).

        Args:
            type_name: Type name
            recursive: If True, returns all descendants,
                      otherwise only direct children

        Returns:
            Set of subtype names
        """
        if type_name not in self._hierarchy:
            return set()

        if recursive:
            # All descendants (full transitivity)
            return set(nx.descendants(self._hierarchy, type_name))
        else:
            # Only direct children
            return set(self._hierarchy.successors(type_name))

    def is_subtype_of(self, child: str, parent: str) -> bool:
        """
        Check subsumption relation (transitive).

        Args:
            child: Potential child type name
            parent: Potential parent type name

        Returns:
            True if child is a subtype of parent (direct or transitive)

        Example:
            >>> registry.is_subtype_of("physical_address", "Place")
            True  # physical_address → PostalAddress → Place
        """
        if child not in self._hierarchy or parent not in self._hierarchy:
            return False

        # Check if parent is in the ancestors of child
        return parent in nx.ancestors(self._hierarchy, child)

    def compute_distance_wu_palmer(self, type1: str, type2: str) -> float:
        """
        Compute Wu & Palmer semantic distance.

        Hierarchy-based algorithm:
        sim(c1, c2) = 2 * depth(LCS) / (depth(c1) + depth(c2))

        where LCS = Lowest Common Subsumer (closest common ancestor)

        Args:
            type1: First type
            type2: Second type

        Returns:
            Similarity between 0.0 (none) and 1.0 (identical)

        Example:
            >>> registry.compute_distance_wu_palmer("email_address", "phone_number")
            0.67  # Shares ContactPoint parent
            >>> registry.compute_distance_wu_palmer("email_address", "email_address")
            1.0  # Identical
        """
        # Identical case
        if type1 == type2:
            return 1.0

        # Check that types are in the hierarchy
        if type1 not in self._hierarchy or type2 not in self._hierarchy:
            return 0.0

        # Find ancestors for each type
        ancestors1 = set(nx.ancestors(self._hierarchy, type1)) | {type1}
        ancestors2 = set(nx.ancestors(self._hierarchy, type2)) | {type2}

        # Find common ancestors
        common = ancestors1 & ancestors2

        if not common:
            # No common ancestor
            return 0.0

        # LCS = deepest common ancestor (closest)
        # Take the one with the longest path from root
        lcs = max(common, key=lambda n: len(self.get_hierarchy_path(n)))

        # Compute depths
        depth_lcs = len(self.get_hierarchy_path(lcs))
        depth1 = len(self.get_hierarchy_path(type1))
        depth2 = len(self.get_hierarchy_path(type2))

        # Formule Wu & Palmer
        if depth1 + depth2 == 0:
            return 0.0

        similarity = (2.0 * depth_lcs) / (depth1 + depth2)
        return similarity

    def get_related_types(self, type_name: str, relation: str = "related") -> set[str]:
        """
        Retrieve types linked by a semantic relation.

        Args:
            type_name: Type name
            relation: Relation type ("related", "broader", "narrower")

        Returns:
            Set of related type names
        """
        if type_name not in self._relations:
            return set()

        related = set()
        for _, target, edge_data in self._relations.edges(type_name, data=True):
            if edge_data.get("relation") == relation:
                related.add(target)

        return related

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
            "relation_edges": self._relations.number_of_edges(),
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
