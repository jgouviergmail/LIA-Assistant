"""
Integration tests for i18n_patterns module.

Tests that multilingual patterns work correctly with the ReferenceResolver.
"""

import pytest

from src.core.i18n_patterns import (
    get_keyword_map,
    get_ordinal_map,
    get_ordinal_suffix_patterns,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.resolver import ReferenceResolver


@pytest.fixture(autouse=True, scope="module")
def register_contacts_context():
    """Register contacts context type for tests without importing full module."""
    # Register minimal definition needed for resolver tests
    if "contacts" not in ContextTypeRegistry.list_all():
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain="contacts",
                agent_name="contacts_agent",
                primary_id_field="resource_name",
                display_name_field="name",
                reference_fields=["name", "emails", "phones"],
                icon="X",  # Using X instead of emoji
            )
        )
    yield


class TestResolverWithI18nPatterns:
    """Tests for ReferenceResolver using i18n patterns."""

    @pytest.fixture
    def sample_items(self):
        """Sample items for resolution tests."""
        return [
            {"index": 1, "name": "Jean Dupont", "email": "jean@example.com"},
            {"index": 2, "name": "Marie Martin", "email": "marie@example.com"},
            {"index": 3, "name": "Pierre Durand", "email": "pierre@example.com"},
            {"index": 4, "name": "Sophie Bernard", "email": "sophie@example.com"},
            {"index": 5, "name": "Lucas Petit", "email": "lucas@example.com"},
        ]

    @pytest.fixture
    def resolver(self):
        """Create resolver with contacts definition."""
        definition = ContextTypeRegistry.get_definition("contacts")
        return ReferenceResolver(definition)

    def test_french_ordinals_resolution(self, resolver, sample_items):
        """Test resolving French ordinal words."""
        # Premier
        result = resolver.resolve("premier", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # Deuxième
        result = resolver.resolve("deuxième", sample_items)
        assert result.success
        assert result.item["name"] == "Marie Martin"

        # Dernier
        result = resolver.resolve("dernier", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_english_ordinals_resolution(self, resolver, sample_items):
        """Test resolving English ordinal words."""
        # First
        result = resolver.resolve("first", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # Second
        result = resolver.resolve("second", sample_items)
        assert result.success
        assert result.item["name"] == "Marie Martin"

        # Last
        result = resolver.resolve("last", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_spanish_ordinals_resolution(self, resolver, sample_items):
        """Test resolving Spanish ordinal words."""
        # Primero
        result = resolver.resolve("primero", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # Último
        result = resolver.resolve("último", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_german_ordinals_resolution(self, resolver, sample_items):
        """Test resolving German ordinal words."""
        # Erste
        result = resolver.resolve("erste", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # Letzter
        result = resolver.resolve("letzter", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_italian_ordinals_resolution(self, resolver, sample_items):
        """Test resolving Italian ordinal words."""
        # Primo
        result = resolver.resolve("primo", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # Ultimo
        result = resolver.resolve("ultimo", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_chinese_ordinals_resolution(self, resolver, sample_items):
        """Test resolving Chinese ordinal words."""
        # 第一
        result = resolver.resolve("第一", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # 最后
        result = resolver.resolve("最后", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_numeric_suffixes_french(self, resolver, sample_items):
        """Test resolving French numeric suffixes."""
        # 2ème
        result = resolver.resolve("2ème", sample_items)
        assert result.success
        assert result.item["name"] == "Marie Martin"

        # 1er
        result = resolver.resolve("1er", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

    def test_numeric_suffixes_english(self, resolver, sample_items):
        """Test resolving English numeric suffixes."""
        # 1st
        result = resolver.resolve("1st", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # 2nd
        result = resolver.resolve("2nd", sample_items)
        assert result.success
        assert result.item["name"] == "Marie Martin"

        # 3rd
        result = resolver.resolve("3rd", sample_items)
        assert result.success
        assert result.item["name"] == "Pierre Durand"

        # 4th
        result = resolver.resolve("4th", sample_items)
        assert result.success
        assert result.item["name"] == "Sophie Bernard"

    def test_plain_numbers(self, resolver, sample_items):
        """Test resolving plain numbers."""
        for i in range(1, 6):
            result = resolver.resolve(str(i), sample_items)
            assert result.success
            assert result.item["index"] == i

    def test_mixed_language_session(self, resolver, sample_items):
        """Test that resolver handles mixed languages in same session."""
        # User might switch languages
        languages_tests = [
            ("premier", "Jean Dupont"),
            ("last", "Lucas Petit"),
            ("tercero", "Pierre Durand"),
            ("zweite", "Marie Martin"),
            ("quinto", "Lucas Petit"),
        ]

        for reference, expected_name in languages_tests:
            result = resolver.resolve(reference, sample_items)
            assert result.success, f"Failed to resolve '{reference}'"
            assert result.item["name"] == expected_name

    def test_article_removal(self, resolver, sample_items):
        """Test that articles are correctly removed."""
        # French with article
        result = resolver.resolve("la première", sample_items)
        assert result.success
        assert result.item["name"] == "Jean Dupont"

        # English with article
        result = resolver.resolve("the last", sample_items)
        assert result.success
        assert result.item["name"] == "Lucas Petit"

    def test_case_insensitivity(self, resolver, sample_items):
        """Test that resolution is case-insensitive."""
        test_cases = [
            ("PREMIER", "Jean Dupont"),
            ("Premier", "Jean Dupont"),
            ("LAST", "Lucas Petit"),
            ("Last", "Lucas Petit"),
        ]

        for reference, expected_name in test_cases:
            result = resolver.resolve(reference, sample_items)
            assert result.success
            assert result.item["name"] == expected_name


@pytest.mark.integration
class TestI18nPatternsConsistency:
    """Tests for i18n patterns data consistency."""

    def test_all_ordinal_maps_consistent(self):
        """Test that all ordinal maps have consistent structure."""
        ordinal_map = get_ordinal_map()

        # All values should be positive integers
        for word, value in ordinal_map.items():
            assert isinstance(value, int)
            assert 1 <= value <= 10, f"Ordinal '{word}' has value {value}"

    def test_all_keyword_maps_consistent(self):
        """Test that all keyword maps have consistent structure."""
        keyword_map = get_keyword_map()

        # Values should be -1 (last) or 1 (first)
        for word, value in keyword_map.items():
            assert value in [-1, 1], f"Keyword '{word}' has unexpected value {value}"

    def test_ordinal_suffix_patterns_compile(self):
        """Test that all patterns compile without errors."""
        import re

        patterns = get_ordinal_suffix_patterns()

        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                pytest.fail(f"Pattern '{pattern}' failed to compile: {e}")

    def test_combined_maps_no_conflicts(self):
        """Test that combined maps don't have conflicting values."""
        ordinal_map = get_ordinal_map()
        keyword_map = get_keyword_map()

        # Check for words that appear in both maps with different values
        common_words = set(ordinal_map.keys()) & set(keyword_map.keys())

        for word in common_words:
            ordinal_value = ordinal_map[word]
            keyword_value = keyword_map[word]

            # For common words like "premier/first", they should map to 1 in both
            if keyword_value == 1:
                assert (
                    ordinal_value == 1
                ), f"Conflict for '{word}': ordinal={ordinal_value}, keyword={keyword_value}"
