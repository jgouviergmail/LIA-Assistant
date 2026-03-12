"""
Unit tests for i18n_patterns module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires (Session 6)
Created: 2025-11-20
"""

from unittest.mock import patch

from src.core.i18n_patterns import (
    KEYWORD_MAPS,
    ORDINAL_MAPS,
    ORDINAL_SUFFIX_PATTERNS,
    get_all_keywords,
    get_all_ordinal_words,
    get_keyword_map,
    get_ordinal_map,
    get_ordinal_suffix_patterns,
)


class TestGetOrdinalMap:
    def test_get_ordinal_map_specific_language(self):
        """Test getting ordinal map for specific language."""
        fr_map = get_ordinal_map("fr")

        assert "premier" in fr_map
        assert fr_map["premier"] == 1
        assert "deuxième" in fr_map
        assert fr_map["deuxième"] == 2

    def test_get_ordinal_map_all_languages(self):
        """Test getting combined ordinal map for all languages."""
        all_map = get_ordinal_map(None)

        # Should contain words from all languages
        assert "premier" in all_map  # French
        assert "first" in all_map  # English
        assert "primero" in all_map  # Spanish
        assert "erste" in all_map  # German
        assert "primo" in all_map  # Italian
        assert "第一" in all_map  # Chinese

    def test_get_ordinal_map_english(self):
        """Test English ordinal mappings."""
        en_map = get_ordinal_map("en")

        assert en_map["first"] == 1
        assert en_map["second"] == 2
        assert en_map["third"] == 3
        assert en_map["tenth"] == 10

    @patch("src.core.i18n_patterns.settings")
    def test_get_ordinal_map_fallback_to_default(self, mock_settings):
        """Test fallback to default language for unsupported language."""
        mock_settings.default_language = "fr"

        # Request unsupported language, should fallback
        result = get_ordinal_map("unsupported")

        assert "premier" in result


class TestGetKeywordMap:
    def test_get_keyword_map_specific_language(self):
        """Test getting keyword map for specific language."""
        fr_map = get_keyword_map("fr")

        assert "dernier" in fr_map
        assert fr_map["dernier"] == -1
        assert "premier" in fr_map
        assert fr_map["premier"] == 1

    def test_get_keyword_map_all_languages(self):
        """Test getting combined keyword map for all languages."""
        all_map = get_keyword_map(None)

        # Should contain keywords from all languages
        assert "dernier" in all_map  # French
        assert "last" in all_map  # English
        assert "último" in all_map  # Spanish
        assert "letzter" in all_map  # German
        assert "ultimo" in all_map  # Italian
        assert "最后" in all_map  # Chinese

    def test_get_keyword_map_last_values(self):
        """Test that 'last' keywords map to -1."""
        en_map = get_keyword_map("en")
        fr_map = get_keyword_map("fr")

        assert en_map["last"] == -1
        assert fr_map["dernier"] == -1

    @patch("src.core.i18n_patterns.settings")
    def test_get_keyword_map_fallback_to_default(self, mock_settings):
        """Test fallback to default language for unsupported language."""
        mock_settings.default_language = "en"

        result = get_keyword_map("unsupported")

        assert "last" in result


class TestGetOrdinalSuffixPatterns:
    def test_get_ordinal_suffix_patterns_specific_language(self):
        """Test getting ordinal suffix patterns for specific language."""
        fr_patterns = get_ordinal_suffix_patterns("fr")

        assert isinstance(fr_patterns, list)
        assert len(fr_patterns) >= 2
        # Should have plain number and French suffix patterns
        assert any(r"\d+" in p for p in fr_patterns)

    def test_get_ordinal_suffix_patterns_all_languages(self):
        """Test getting combined patterns for all languages."""
        all_patterns = get_ordinal_suffix_patterns(None)

        assert isinstance(all_patterns, list)
        assert len(all_patterns) > 0
        # Should be unique (no duplicates)
        assert len(all_patterns) == len(set(all_patterns))

    def test_get_ordinal_suffix_patterns_english(self):
        """Test English ordinal suffix patterns."""
        en_patterns = get_ordinal_suffix_patterns("en")

        # Should have patterns for st, nd, rd, th
        patterns_str = "".join(en_patterns)
        assert "st" in patterns_str
        assert "nd" in patterns_str
        assert "rd" in patterns_str
        assert "th" in patterns_str

    @patch("src.core.i18n_patterns.settings")
    def test_get_ordinal_suffix_patterns_fallback(self, mock_settings):
        """Test fallback to default language."""
        mock_settings.default_language = "fr"

        result = get_ordinal_suffix_patterns("unsupported")

        assert isinstance(result, list)
        assert len(result) > 0


class TestGetAllOrdinalWords:
    def test_get_all_ordinal_words_returns_set(self):
        """Test that get_all_ordinal_words returns a set."""
        words = get_all_ordinal_words()

        assert isinstance(words, set)

    def test_get_all_ordinal_words_contains_multiple_languages(self):
        """Test that result contains words from multiple languages."""
        words = get_all_ordinal_words()

        # Should contain French words
        assert "premier" in words or "première" in words
        # Should contain English words
        assert "first" in words
        # Should contain Spanish words
        assert "primero" in words or "primera" in words

    def test_get_all_ordinal_words_lowercase(self):
        """Test that all words are lowercase."""
        words = get_all_ordinal_words()

        for word in words:
            assert word == word.lower()

    def test_get_all_ordinal_words_unique(self):
        """Test that all words are unique (set property)."""
        words = get_all_ordinal_words()
        words_list = list(words)

        # Set should have no duplicates
        assert len(words) == len(words_list)


class TestGetAllKeywords:
    def test_get_all_keywords_returns_set(self):
        """Test that get_all_keywords returns a set."""
        keywords = get_all_keywords()

        assert isinstance(keywords, set)

    def test_get_all_keywords_contains_multiple_languages(self):
        """Test that result contains keywords from multiple languages."""
        keywords = get_all_keywords()

        # Should contain 'last' variants
        assert "dernier" in keywords or "dernière" in keywords
        assert "last" in keywords
        assert "último" in keywords or "ultimo" in keywords

    def test_get_all_keywords_lowercase(self):
        """Test that all keywords are lowercase."""
        keywords = get_all_keywords()

        for keyword in keywords:
            assert keyword == keyword.lower()

    def test_get_all_keywords_unique(self):
        """Test that all keywords are unique."""
        keywords = get_all_keywords()
        keywords_list = list(keywords)

        assert len(keywords) == len(keywords_list)


class TestDataStructures:
    def test_ordinal_maps_structure(self):
        """Test ORDINAL_MAPS has correct structure."""
        assert isinstance(ORDINAL_MAPS, dict)
        assert "fr" in ORDINAL_MAPS
        assert "en" in ORDINAL_MAPS

        # Each language should have word -> int mappings
        for _lang, mappings in ORDINAL_MAPS.items():
            assert isinstance(mappings, dict)
            for word, value in mappings.items():
                assert isinstance(word, str)
                assert isinstance(value, int)
                assert value > 0  # Ordinals are 1-indexed

    def test_keyword_maps_structure(self):
        """Test KEYWORD_MAPS has correct structure."""
        assert isinstance(KEYWORD_MAPS, dict)
        assert "fr" in KEYWORD_MAPS
        assert "en" in KEYWORD_MAPS

        # Each language should have word -> int mappings
        for _lang, mappings in KEYWORD_MAPS.items():
            assert isinstance(mappings, dict)
            for word, value in mappings.items():
                assert isinstance(word, str)
                assert isinstance(value, int)
                # Keywords can be positive (first) or negative (last)
                assert value == 1 or value == -1

    def test_ordinal_suffix_patterns_structure(self):
        """Test ORDINAL_SUFFIX_PATTERNS has correct structure."""
        assert isinstance(ORDINAL_SUFFIX_PATTERNS, dict)
        assert "fr" in ORDINAL_SUFFIX_PATTERNS
        assert "en" in ORDINAL_SUFFIX_PATTERNS

        # Each language should have list of regex patterns
        for _lang, patterns in ORDINAL_SUFFIX_PATTERNS.items():
            assert isinstance(patterns, list)
            assert len(patterns) > 0
            for pattern in patterns:
                assert isinstance(pattern, str)
                # Should be regex patterns
                assert r"(\d+)" in pattern

    def test_all_languages_present(self):
        """Test that all 6 languages are present in all maps."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}

        assert set(ORDINAL_MAPS.keys()) == expected_languages
        assert set(KEYWORD_MAPS.keys()) == expected_languages
        assert set(ORDINAL_SUFFIX_PATTERNS.keys()) == expected_languages
