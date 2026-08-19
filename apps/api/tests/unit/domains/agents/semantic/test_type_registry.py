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

    def test_register_updates_domain_index(self, registry, sample_types):
        """Test that register updates domain index."""
        registry.register(sample_types["email"])

        types_by_domain = registry.get_by_domain("contact")
        assert "email_address" in types_by_domain

        types_by_domain = registry.get_by_domain("email")
        assert "email_address" in types_by_domain


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


class TestLivingSurface:
    """Coverage of the API that survived ADR-233 (register/get/by_domain/stats).

    The transitive-subsumption / Wu & Palmer / SKOS / category-tool getters
    were removed with their tests (zero runtime consumers); this class keeps
    the RETAINED surface pinned so the purge cannot silently rot it.
    """

    def test_register_and_get(self, registry, sample_types):
        registry.register(sample_types["thing"])
        registry.register(sample_types["contact"])
        assert registry.get("Contact") is sample_types["contact"]
        assert registry.get("missing") is None
        assert len(registry) == 2
        assert "Contact" in registry

    def test_duplicate_registration_is_skipped(self, registry, sample_types):
        registry.register(sample_types["thing"])
        registry.register(sample_types["thing"])
        assert len(registry) == 1

    def test_get_by_domain_index(self, registry, sample_types):
        registry.register(sample_types["contact"])
        assert registry.get_by_domain("contact") == {"Contact"}
        assert registry.get_by_domain("unknown") == set()

    def test_get_all_returns_every_type(self, registry, sample_types):
        for t in sample_types.values():
            registry.register(t)
        assert {t.name for t in registry.get_all()} == {t.name for t in sample_types.values()}

    def test_validate_hierarchy_flags_missing_parent(self, registry):
        registry.register(
            SemanticType(name="orphan", parent="ghost", category=TypeCategory.IDENTITY)
        )
        errors = registry.validate_hierarchy()
        assert any("ghost" in e for e in errors)

    def test_get_stats_shape(self, registry, sample_types):
        registry.register(sample_types["contact"])
        stats = registry.get_stats()
        assert stats["total_types"] == 1
        assert stats["total_domains"] == 1
        assert stats["total_tools"] == 1

    def test_global_singleton_roundtrip(self):
        reset_registry()
        assert get_registry() is get_registry()
        reset_registry()
