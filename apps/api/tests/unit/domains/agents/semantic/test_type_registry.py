"""
Unit tests for semantic type registry.

Tests for TypeRegistry class that manages semantic types.
"""

import pytest

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import (
    TypeRegistry,
    get_registry,
    reset_registry,
)


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return TypeRegistry()


@pytest.fixture
def sample_types():
    """Create sample types for testing."""
    return {
        "thing": SemanticType(
            name="Thing",
            category=TypeCategory.IDENTITY,
            description="Root type",
        ),
        "person": SemanticType(
            name="Person",
            parent="Thing",
            category=TypeCategory.IDENTITY,
            description="A person",
        ),
        "contact": SemanticType(
            name="Contact",
            parent="Person",
            category=TypeCategory.IDENTITY,
            description="A contact",
            source_domains=["contact"],
            used_in_tools=["get_contact_tool"],
        ),
        "email": SemanticType(
            name="email_address",
            parent="Contact",
            category=TypeCategory.IDENTITY,
            description="Email address",
            related_types=["phone_number", "person_name"],
            source_domains=["contact", "email"],
            used_in_tools=["get_contact_tool", "send_email_tool"],
        ),
        "phone": SemanticType(
            name="phone_number",
            parent="Contact",
            category=TypeCategory.IDENTITY,
            description="Phone number",
            related_types=["email_address"],
            source_domains=["contact"],
        ),
    }


@pytest.fixture
def populated_registry(registry, sample_types):
    """Create registry with sample types."""
    for type_def in sample_types.values():
        registry.register(type_def)
    return registry


class TestTypeRegistryInit:
    """Tests for TypeRegistry initialization."""

    def test_init_creates_empty_registry(self, registry):
        """Test that init creates empty registry."""
        assert len(registry) == 0
        assert registry.get_all() == []

    def test_init_creates_category_indexes(self, registry):
        """Test that init creates category indexes."""
        for category in TypeCategory:
            assert registry.get_by_category(category) == set()


class TestTypeRegistryRegister:
    """Tests for register method."""

    def test_register_adds_type(self, registry):
        """Test that register adds type to registry."""
        type_def = SemanticType(name="test_type", category=TypeCategory.IDENTITY)
        registry.register(type_def)

        assert "test_type" in registry
        assert registry.get("test_type") == type_def

    def test_register_skips_duplicate(self, registry):
        """Test that register skips already registered type."""
        type_def = SemanticType(name="test_type", category=TypeCategory.IDENTITY)
        registry.register(type_def)
        registry.register(type_def)

        assert len(registry) == 1

    def test_register_builds_hierarchy(self, registry, sample_types):
        """Test that register builds parent-child hierarchy."""
        registry.register(sample_types["thing"])
        registry.register(sample_types["person"])

        # Check hierarchy is built
        subtypes = registry.get_subtypes("Thing")
        assert "Person" in subtypes

    def test_register_builds_semantic_relations(self, registry, sample_types):
        """Test that register builds semantic relations."""
        registry.register(sample_types["email"])
        registry.register(sample_types["phone"])

        related = registry.get_related_types("email_address", "related")
        assert "phone_number" in related

    def test_register_updates_domain_index(self, registry, sample_types):
        """Test that register updates domain index."""
        registry.register(sample_types["email"])

        types_by_domain = registry.get_by_domain("contact")
        assert "email_address" in types_by_domain

        types_by_domain = registry.get_by_domain("email")
        assert "email_address" in types_by_domain

    def test_register_updates_tool_index(self, registry, sample_types):
        """Test that register updates tool index."""
        registry.register(sample_types["email"])

        types_by_tool = registry.get_by_tool("get_contact_tool")
        assert "email_address" in types_by_tool

        types_by_tool = registry.get_by_tool("send_email_tool")
        assert "email_address" in types_by_tool

    def test_register_updates_category_index(self, registry, sample_types):
        """Test that register updates category index."""
        registry.register(sample_types["email"])

        types_by_category = registry.get_by_category(TypeCategory.IDENTITY)
        assert "email_address" in types_by_category


class TestTypeRegistryGet:
    """Tests for get methods."""

    def test_get_returns_registered_type(self, populated_registry):
        """Test that get returns registered type."""
        result = populated_registry.get("email_address")

        assert result is not None
        assert result.name == "email_address"

    def test_get_returns_none_for_unknown(self, registry):
        """Test that get returns None for unknown type."""
        result = registry.get("unknown_type")
        assert result is None

    def test_get_all_returns_all_types(self, populated_registry):
        """Test that get_all returns all registered types."""
        all_types = populated_registry.get_all()

        assert len(all_types) == 5
        names = {t.name for t in all_types}
        assert "Thing" in names
        assert "email_address" in names


class TestTypeRegistryByCategory:
    """Tests for get_by_category method."""

    def test_get_by_category_returns_matching(self, populated_registry):
        """Test that get_by_category returns matching types."""
        result = populated_registry.get_by_category(TypeCategory.IDENTITY)

        assert "Thing" in result
        assert "Person" in result
        assert "email_address" in result

    def test_get_by_category_returns_empty_for_no_match(self, populated_registry):
        """Test that get_by_category returns empty for no matches."""
        result = populated_registry.get_by_category(TypeCategory.LOCATION)
        assert result == set()


class TestTypeRegistryByDomain:
    """Tests for get_by_domain method."""

    def test_get_by_domain_returns_matching(self, populated_registry):
        """Test that get_by_domain returns matching types."""
        result = populated_registry.get_by_domain("contact")

        assert "Contact" in result
        assert "email_address" in result
        assert "phone_number" in result

    def test_get_by_domain_returns_empty_for_unknown(self, populated_registry):
        """Test that get_by_domain returns empty for unknown domain."""
        result = populated_registry.get_by_domain("unknown_domain")
        assert result == set()


class TestTypeRegistryByTool:
    """Tests for get_by_tool method."""

    def test_get_by_tool_returns_matching(self, populated_registry):
        """Test that get_by_tool returns matching types."""
        result = populated_registry.get_by_tool("get_contact_tool")

        assert "Contact" in result
        assert "email_address" in result

    def test_get_by_tool_returns_empty_for_unknown(self, populated_registry):
        """Test that get_by_tool returns empty for unknown tool."""
        result = populated_registry.get_by_tool("unknown_tool")
        assert result == set()


class TestTypeRegistryHierarchy:
    """Tests for hierarchy-related methods."""

    def test_get_hierarchy_path_returns_path(self, populated_registry):
        """Test that get_hierarchy_path returns full path."""
        path = populated_registry.get_hierarchy_path("email_address")

        # Should include ancestors
        assert "Thing" in path
        assert "Person" in path
        assert "Contact" in path
        assert "email_address" in path
        assert path[-1] == "email_address"

    def test_get_hierarchy_path_for_root(self, populated_registry):
        """Test that get_hierarchy_path for root returns single item."""
        path = populated_registry.get_hierarchy_path("Thing")
        assert path == ["Thing"]

    def test_get_hierarchy_path_for_unknown(self, registry):
        """Test that get_hierarchy_path for unknown type returns single item."""
        path = registry.get_hierarchy_path("unknown_type")
        assert path == ["unknown_type"]

    def test_get_subtypes_recursive(self, populated_registry):
        """Test that get_subtypes returns all descendants."""
        subtypes = populated_registry.get_subtypes("Thing", recursive=True)

        assert "Person" in subtypes
        assert "Contact" in subtypes
        assert "email_address" in subtypes
        assert "phone_number" in subtypes

    def test_get_subtypes_non_recursive(self, populated_registry):
        """Test that get_subtypes returns only direct children."""
        subtypes = populated_registry.get_subtypes("Thing", recursive=False)

        assert "Person" in subtypes
        assert "Contact" not in subtypes
        assert "email_address" not in subtypes

    def test_get_subtypes_for_leaf(self, populated_registry):
        """Test that get_subtypes for leaf returns empty."""
        subtypes = populated_registry.get_subtypes("email_address")
        assert subtypes == set()

    def test_is_subtype_of_direct_parent(self, populated_registry):
        """Test that is_subtype_of returns True for direct parent."""
        assert populated_registry.is_subtype_of("Person", "Thing") is True

    def test_is_subtype_of_transitive(self, populated_registry):
        """Test that is_subtype_of returns True for transitive parent."""
        assert populated_registry.is_subtype_of("email_address", "Thing") is True
        assert populated_registry.is_subtype_of("email_address", "Person") is True

    def test_is_subtype_of_returns_false_for_non_parent(self, populated_registry):
        """Test that is_subtype_of returns False for non-parent."""
        assert populated_registry.is_subtype_of("Thing", "Person") is False
        assert populated_registry.is_subtype_of("email_address", "phone_number") is False

    def test_is_subtype_of_returns_false_for_unknown(self, registry):
        """Test that is_subtype_of returns False for unknown types."""
        assert registry.is_subtype_of("unknown1", "unknown2") is False


class TestTypeRegistryWuPalmer:
    """Tests for Wu & Palmer distance calculation."""

    def test_distance_identical_types(self, populated_registry):
        """Test that identical types have distance 1.0."""
        distance = populated_registry.compute_distance_wu_palmer("email_address", "email_address")
        assert distance == 1.0

    def test_distance_sibling_types(self, populated_registry):
        """Test distance for sibling types."""
        distance = populated_registry.compute_distance_wu_palmer("email_address", "phone_number")

        # Both are children of Contact, should have high similarity
        assert 0.5 < distance < 1.0

    def test_distance_parent_child(self, populated_registry):
        """Test distance for parent-child types."""
        distance = populated_registry.compute_distance_wu_palmer("Contact", "email_address")

        # Parent-child should have similarity
        assert 0.5 < distance < 1.0

    def test_distance_distant_types(self, populated_registry):
        """Test distance for more distant types."""
        distance = populated_registry.compute_distance_wu_palmer("Thing", "email_address")

        # Distant types should have lower similarity
        assert distance < 0.8

    def test_distance_unknown_types(self, registry):
        """Test that unknown types have distance 0.0."""
        distance = registry.compute_distance_wu_palmer("unknown1", "unknown2")
        assert distance == 0.0


class TestTypeRegistryRelatedTypes:
    """Tests for get_related_types method."""

    def test_get_related_types_returns_related(self, populated_registry):
        """Test that get_related_types returns related types."""
        related = populated_registry.get_related_types("email_address", "related")

        assert "phone_number" in related

    def test_get_related_types_returns_empty_for_unknown(self, registry):
        """Test that get_related_types returns empty for unknown type."""
        related = registry.get_related_types("unknown_type", "related")
        assert related == set()

    def test_get_related_types_filters_by_relation(self, registry):
        """Test that get_related_types filters by relation type."""
        type_def = SemanticType(
            name="test_type",
            category=TypeCategory.IDENTITY,
            related_types=["related1"],
            broader_types=["broader1"],
        )
        registry.register(type_def)

        related = registry.get_related_types("test_type", "related")
        assert "related1" in related
        assert "broader1" not in related

        broader = registry.get_related_types("test_type", "broader")
        assert "broader1" in broader
        assert "related1" not in broader


class TestTypeRegistryValidation:
    """Tests for validate_hierarchy method."""

    def test_validate_hierarchy_returns_empty_for_valid(self, populated_registry):
        """Test that validate_hierarchy returns empty for valid registry."""
        errors = populated_registry.validate_hierarchy()
        assert errors == []

    def test_validate_hierarchy_detects_missing_parent(self, registry):
        """Test that validate_hierarchy detects missing parent."""
        type_def = SemanticType(
            name="orphan",
            parent="nonexistent_parent",
            category=TypeCategory.IDENTITY,
        )
        registry.register(type_def)

        errors = registry.validate_hierarchy()
        assert len(errors) == 1
        assert "nonexistent_parent" in errors[0]


class TestTypeRegistryStats:
    """Tests for get_stats method."""

    def test_get_stats_returns_correct_counts(self, populated_registry):
        """Test that get_stats returns correct statistics."""
        stats = populated_registry.get_stats()

        assert stats["total_types"] == 5
        assert stats["total_domains"] == 2  # contact, email
        assert stats["hierarchy_nodes"] > 0
        assert stats["hierarchy_edges"] > 0


class TestTypeRegistryDunderMethods:
    """Tests for dunder methods."""

    def test_len_returns_type_count(self, populated_registry):
        """Test that __len__ returns type count."""
        assert len(populated_registry) == 5

    def test_contains_returns_true_for_registered(self, populated_registry):
        """Test that __contains__ returns True for registered type."""
        assert "email_address" in populated_registry

    def test_contains_returns_false_for_unregistered(self, populated_registry):
        """Test that __contains__ returns False for unregistered type."""
        assert "unknown_type" not in populated_registry

    def test_repr_includes_counts(self, populated_registry):
        """Test that __repr__ includes useful info."""
        result = repr(populated_registry)

        assert "TypeRegistry" in result
        assert "types=" in result


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def setup_method(self):
        """Reset global registry before each test."""
        reset_registry()

    def teardown_method(self):
        """Reset global registry after each test."""
        reset_registry()

    def test_get_registry_returns_singleton(self):
        """Test that get_registry returns same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_get_registry_creates_instance(self):
        """Test that get_registry creates new instance if none exists."""
        registry = get_registry()
        assert registry is not None
        assert isinstance(registry, TypeRegistry)

    def test_reset_registry_clears_singleton(self):
        """Test that reset_registry clears the global instance."""
        registry1 = get_registry()
        reset_registry()
        registry2 = get_registry()

        assert registry1 is not registry2

    def test_reset_registry_allows_fresh_start(self):
        """Test that reset allows fresh start."""
        registry1 = get_registry()
        type_def = SemanticType(name="test", category=TypeCategory.IDENTITY)
        registry1.register(type_def)

        reset_registry()
        registry2 = get_registry()

        assert "test" not in registry2
