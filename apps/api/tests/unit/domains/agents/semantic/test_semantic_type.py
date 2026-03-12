"""
Unit tests for semantic type system.

Tests for TypeCategory enum and SemanticType dataclass.
"""

import pytest

from src.domains.agents.semantic.semantic_type import (
    SemanticType,
    TypeCategory,
)


class TestTypeCategory:
    """Tests for TypeCategory enum."""

    def test_identity_category_exists(self):
        """Test that IDENTITY category exists."""
        assert TypeCategory.IDENTITY.value == "identity"

    def test_location_category_exists(self):
        """Test that LOCATION category exists."""
        assert TypeCategory.LOCATION.value == "location"

    def test_temporal_category_exists(self):
        """Test that TEMPORAL category exists."""
        assert TypeCategory.TEMPORAL.value == "temporal"

    def test_resource_id_category_exists(self):
        """Test that RESOURCE_ID category exists."""
        assert TypeCategory.RESOURCE_ID.value == "resource_id"

    def test_content_category_exists(self):
        """Test that CONTENT category exists."""
        assert TypeCategory.CONTENT.value == "content"

    def test_measurement_category_exists(self):
        """Test that MEASUREMENT category exists."""
        assert TypeCategory.MEASUREMENT.value == "measurement"

    def test_status_category_exists(self):
        """Test that STATUS category exists."""
        assert TypeCategory.STATUS.value == "status"

    def test_category_category_exists(self):
        """Test that CATEGORY category exists."""
        assert TypeCategory.CATEGORY.value == "category"

    def test_all_categories_are_unique(self):
        """Test that all category values are unique."""
        values = [cat.value for cat in TypeCategory]
        assert len(values) == len(set(values))


class TestSemanticTypeInitialization:
    """Tests for SemanticType initialization."""

    def test_minimal_initialization(self):
        """Test creation with minimal required fields."""
        semantic_type = SemanticType(
            name="test_type",
            category=TypeCategory.IDENTITY,
        )

        assert semantic_type.name == "test_type"
        assert semantic_type.category == TypeCategory.IDENTITY
        assert semantic_type.uri is None
        assert semantic_type.parent is None
        assert semantic_type.children == []
        assert semantic_type.description == ""
        assert semantic_type.examples == []
        assert semantic_type.labels == {}
        assert semantic_type.properties == {}
        assert semantic_type.related_types == []
        assert semantic_type.source_domains == []
        assert semantic_type.used_in_tools == []
        assert semantic_type.format_pattern is None
        assert semantic_type.validation_rules == []

    def test_full_initialization(self):
        """Test creation with all fields."""
        semantic_type = SemanticType(
            name="email_address",
            category=TypeCategory.IDENTITY,
            uri="http://schema.org/email",
            parent="ContactPoint",
            children=["work_email", "personal_email"],
            description="Email address (RFC 5322 compliant)",
            examples=["john@example.com", "user+tag@domain.co.uk"],
            labels={"en": "Email address", "fr": "Adresse email"},
            properties={"domain": "str", "local_part": "str"},
            related_types=["contact_id", "person_name"],
            broader_types=["ContactPoint"],
            narrower_types=["work_email"],
            source_domains=["contact", "email"],
            used_in_tools=["get_contact_tool", "send_email_tool"],
            format_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            validation_rules=["Must be RFC 5322 compliant"],
        )

        assert semantic_type.name == "email_address"
        assert semantic_type.uri == "http://schema.org/email"
        assert semantic_type.parent == "ContactPoint"
        assert "work_email" in semantic_type.children
        assert semantic_type.description == "Email address (RFC 5322 compliant)"
        assert "john@example.com" in semantic_type.examples
        assert semantic_type.labels["fr"] == "Adresse email"
        assert semantic_type.properties["domain"] == "str"
        assert "contact_id" in semantic_type.related_types
        assert "ContactPoint" in semantic_type.broader_types
        assert "work_email" in semantic_type.narrower_types
        assert "contact" in semantic_type.source_domains
        assert "get_contact_tool" in semantic_type.used_in_tools
        assert semantic_type.format_pattern is not None
        assert "Must be RFC 5322 compliant" in semantic_type.validation_rules

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            SemanticType(name="", category=TypeCategory.IDENTITY)

    def test_name_with_spaces_raises_error(self):
        """Test that name with spaces raises ValueError."""
        with pytest.raises(ValueError, match="cannot contain spaces"):
            SemanticType(name="my type", category=TypeCategory.IDENTITY)

    def test_name_with_underscores_is_valid(self):
        """Test that name with underscores is valid."""
        semantic_type = SemanticType(
            name="my_type_with_underscores",
            category=TypeCategory.IDENTITY,
        )
        assert semantic_type.name == "my_type_with_underscores"

    def test_is_frozen_dataclass(self):
        """Test that SemanticType is immutable (frozen)."""
        semantic_type = SemanticType(
            name="frozen_type",
            category=TypeCategory.IDENTITY,
        )

        with pytest.raises(AttributeError):
            semantic_type.name = "new_name"


class TestSemanticTypeGetLabel:
    """Tests for get_label method."""

    @pytest.fixture
    def multilingual_type(self):
        """Create a type with multiple language labels."""
        return SemanticType(
            name="test_type",
            category=TypeCategory.IDENTITY,
            labels={
                "en": "Test Type",
                "fr": "Type de Test",
                "de": "Testtyp",
            },
        )

    @pytest.fixture
    def english_only_type(self):
        """Create a type with English label only."""
        return SemanticType(
            name="english_type",
            category=TypeCategory.IDENTITY,
            labels={"en": "English Type"},
        )

    @pytest.fixture
    def no_labels_type(self):
        """Create a type with no labels."""
        return SemanticType(
            name="no_labels_type",
            category=TypeCategory.IDENTITY,
        )

    def test_get_label_returns_requested_language(self, multilingual_type):
        """Test that get_label returns the correct language."""
        assert multilingual_type.get_label("fr") == "Type de Test"
        assert multilingual_type.get_label("de") == "Testtyp"

    def test_get_label_defaults_to_english(self, multilingual_type):
        """Test that get_label defaults to English when requested language unavailable."""
        result = multilingual_type.get_label("es")  # Spanish not available
        assert result == "Test Type"  # English fallback

    def test_get_label_fallback_to_name_when_no_english(self, no_labels_type):
        """Test that get_label returns name when no labels available."""
        result = no_labels_type.get_label("fr")
        assert result == "no_labels_type"

    def test_get_label_english_fallback_when_not_in_english(self, english_only_type):
        """Test that get_label falls back to English for unavailable languages."""
        result = english_only_type.get_label("fr")
        assert result == "English Type"

    def test_get_label_with_default_lang(self, multilingual_type):
        """Test that get_label uses 'en' as default language."""
        result = multilingual_type.get_label()  # No argument, defaults to 'en'
        assert result == "Test Type"


class TestSemanticTypeIsSubtypeOf:
    """Tests for is_subtype_of method."""

    def test_is_subtype_of_direct_parent(self):
        """Test that is_subtype_of returns True for direct parent."""
        child_type = SemanticType(
            name="child_type",
            category=TypeCategory.IDENTITY,
            parent="parent_type",
        )

        assert child_type.is_subtype_of("parent_type") is True

    def test_is_subtype_of_returns_false_for_non_parent(self):
        """Test that is_subtype_of returns False for non-parent."""
        child_type = SemanticType(
            name="child_type",
            category=TypeCategory.IDENTITY,
            parent="parent_type",
        )

        assert child_type.is_subtype_of("other_type") is False

    def test_is_subtype_of_returns_false_for_none_parent(self):
        """Test that is_subtype_of returns False when no parent."""
        root_type = SemanticType(
            name="root_type",
            category=TypeCategory.IDENTITY,
        )

        assert root_type.is_subtype_of("any_type") is False

    def test_is_subtype_of_self_returns_false(self):
        """Test that is_subtype_of returns False for self."""
        semantic_type = SemanticType(
            name="self_type",
            category=TypeCategory.IDENTITY,
            parent="other_parent",
        )

        assert semantic_type.is_subtype_of("self_type") is False


class TestSemanticTypeToDict:
    """Tests for to_dict method."""

    def test_to_dict_returns_all_fields(self):
        """Test that to_dict returns all fields."""
        semantic_type = SemanticType(
            name="full_type",
            category=TypeCategory.LOCATION,
            uri="http://example.org/full_type",
            parent="parent",
            children=["child1"],
            description="Full type description",
            examples=["example1"],
            labels={"en": "Full Type"},
            properties={"prop1": "str"},
            related_types=["related1"],
            broader_types=["broader1"],
            narrower_types=["narrower1"],
            source_domains=["domain1"],
            used_in_tools=["tool1"],
            format_pattern=r"^\d+$",
            validation_rules=["rule1"],
        )

        result = semantic_type.to_dict()

        assert result["name"] == "full_type"
        assert result["category"] == "location"
        assert result["uri"] == "http://example.org/full_type"
        assert result["parent"] == "parent"
        assert result["children"] == ["child1"]
        assert result["description"] == "Full type description"
        assert result["examples"] == ["example1"]
        assert result["labels"] == {"en": "Full Type"}
        assert result["properties"] == {"prop1": "str"}
        assert result["related_types"] == ["related1"]
        assert result["broader_types"] == ["broader1"]
        assert result["narrower_types"] == ["narrower1"]
        assert result["source_domains"] == ["domain1"]
        assert result["used_in_tools"] == ["tool1"]
        assert result["format_pattern"] == r"^\d+$"
        assert result["validation_rules"] == ["rule1"]

    def test_to_dict_handles_none_values(self):
        """Test that to_dict handles None values correctly."""
        semantic_type = SemanticType(
            name="minimal_type",
            category=TypeCategory.IDENTITY,
        )

        result = semantic_type.to_dict()

        assert result["uri"] is None
        assert result["parent"] is None
        assert result["format_pattern"] is None

    def test_to_dict_returns_category_value_not_enum(self):
        """Test that to_dict returns category value, not enum."""
        semantic_type = SemanticType(
            name="category_test",
            category=TypeCategory.TEMPORAL,
        )

        result = semantic_type.to_dict()

        assert result["category"] == "temporal"
        assert not isinstance(result["category"], TypeCategory)


class TestSemanticTypeRepr:
    """Tests for __repr__ method."""

    def test_repr_minimal(self):
        """Test repr with minimal fields."""
        semantic_type = SemanticType(
            name="minimal",
            category=TypeCategory.IDENTITY,
        )

        result = repr(semantic_type)

        assert "SemanticType" in result
        assert "name=minimal" in result
        assert "category=identity" in result
        assert "parent" not in result  # No parent
        assert "domains" not in result  # No domains

    def test_repr_with_parent(self):
        """Test repr includes parent when present."""
        semantic_type = SemanticType(
            name="child",
            category=TypeCategory.IDENTITY,
            parent="parent",
        )

        result = repr(semantic_type)

        assert "parent=parent" in result

    def test_repr_with_domains(self):
        """Test repr includes domains when present."""
        semantic_type = SemanticType(
            name="with_domains",
            category=TypeCategory.IDENTITY,
            source_domains=["domain1", "domain2"],
        )

        result = repr(semantic_type)

        assert "domains=" in result
        assert "domain1" in result

    def test_repr_with_all(self):
        """Test repr with parent and domains."""
        semantic_type = SemanticType(
            name="full",
            category=TypeCategory.LOCATION,
            parent="parent",
            source_domains=["domain1"],
        )

        result = repr(semantic_type)

        assert "name=full" in result
        assert "category=location" in result
        assert "parent=parent" in result
        assert "domains=" in result


class TestSemanticTypeEquality:
    """Tests for equality and hashing."""

    def test_equal_types_are_equal(self):
        """Test that identical types are equal."""
        type1 = SemanticType(
            name="equal_type",
            category=TypeCategory.IDENTITY,
            description="Same description",
        )
        type2 = SemanticType(
            name="equal_type",
            category=TypeCategory.IDENTITY,
            description="Same description",
        )

        assert type1 == type2

    def test_different_names_not_equal(self):
        """Test that types with different names are not equal."""
        type1 = SemanticType(name="type_a", category=TypeCategory.IDENTITY)
        type2 = SemanticType(name="type_b", category=TypeCategory.IDENTITY)

        assert type1 != type2

    def test_different_categories_not_equal(self):
        """Test that types with different categories are not equal."""
        type1 = SemanticType(name="same_name", category=TypeCategory.IDENTITY)
        type2 = SemanticType(name="same_name", category=TypeCategory.LOCATION)

        assert type1 != type2

    def test_frozen_dataclass_is_immutable(self):
        """Test that frozen dataclass cannot have its attributes changed."""
        semantic_type = SemanticType(
            name="immutable",
            category=TypeCategory.IDENTITY,
        )

        # Should raise when trying to change attribute
        with pytest.raises((AttributeError, TypeError)):
            semantic_type.name = "new_name"
