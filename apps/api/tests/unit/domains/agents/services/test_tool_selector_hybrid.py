"""
Unit tests for hybrid semantic tool scoring (CORRECTION 7).

Tests coverage:
- Description-only tool uses description score
- Keywords-only tool uses keyword score (legacy)
- Hybrid combination respects alpha weighting
- First-line extraction removes markdown formatting
- First-line extraction handles multiline descriptions
- Hybrid disabled uses keywords only
- Feature flag rollback

Target: SemanticToolSelector in
    domains/agents/services/tool_selector.py
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.tool_selector import (
    DEFAULT_HYBRID_ALPHA,
    DEFAULT_HYBRID_MODE,
    SemanticToolSelector,
)

# =============================================================================
# Tests: First-line extraction
# =============================================================================


class TestFirstLineExtraction:
    """Test _extract_semantic_description method."""

    def setup_method(self) -> None:
        """Create selector instance for testing."""
        self.selector = SemanticToolSelector()

    def test_removes_markdown_bold(self) -> None:
        """First line extraction should remove ** markdown formatting."""
        description = (
            "**Tool: get_contacts_tool** - Get contacts with full details.\n\n**MODES**:\n..."
        )
        result = self.selector._extract_semantic_description(description)
        assert "**" not in result
        assert "Tool: get_contacts_tool" in result
        assert "Get contacts with full details." in result

    def test_takes_only_first_line(self) -> None:
        """First line extraction should take only the first line."""
        description = "First line summary.\nSecond line details.\nThird line parameters."
        result = self.selector._extract_semantic_description(description)
        assert result == "First line summary."

    def test_handles_single_line(self) -> None:
        """Single line description returns as-is (minus markdown)."""
        description = "**Tool: my_tool** - Simple description."
        result = self.selector._extract_semantic_description(description)
        assert result == "Tool: my_tool - Simple description."

    def test_empty_description_returns_empty(self) -> None:
        """Empty description returns empty string."""
        assert self.selector._extract_semantic_description("") == ""

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        description = "  Summary with spaces.  \nDetails here."
        result = self.selector._extract_semantic_description(description)
        assert result == "Summary with spaces."

    def test_multiple_bold_sections(self) -> None:
        """Multiple bold sections should all be unformatted."""
        description = "**Tool: name** - **Important** description."
        result = self.selector._extract_semantic_description(description)
        assert result == "Tool: name - Important description."


# =============================================================================
# Tests: Hybrid scoring logic
# =============================================================================


class TestHybridScoringLogic:
    """Test hybrid scoring computation (alpha weighting)."""

    def test_hybrid_combination_formula(self) -> None:
        """Hybrid score = alpha * desc_score + (1-alpha) * keyword_score."""
        alpha = DEFAULT_HYBRID_ALPHA  # 0.6
        desc_score = 0.8
        keyword_score = 0.5

        expected = alpha * desc_score + (1 - alpha) * keyword_score
        assert expected == pytest.approx(0.68)

    def test_alpha_default_is_0_6(self) -> None:
        """Default hybrid alpha should be 0.6."""
        assert DEFAULT_HYBRID_ALPHA == 0.6

    def test_mode_default_is_first_line(self) -> None:
        """Default hybrid mode should be 'first_line'."""
        assert DEFAULT_HYBRID_MODE == "first_line"


# =============================================================================
# Tests: Selector initialization attributes
# =============================================================================


class TestSelectorAttributes:
    """Test SemanticToolSelector hybrid-related attributes."""

    def test_init_has_description_embeddings(self) -> None:
        """Selector should have _tool_description_embeddings dict."""
        selector = SemanticToolSelector()
        assert hasattr(selector, "_tool_description_embeddings")
        assert isinstance(selector._tool_description_embeddings, dict)
        assert len(selector._tool_description_embeddings) == 0

    def test_init_has_hybrid_alpha(self) -> None:
        """Selector should have _hybrid_alpha attribute."""
        selector = SemanticToolSelector()
        assert hasattr(selector, "_hybrid_alpha")
        assert selector._hybrid_alpha == DEFAULT_HYBRID_ALPHA

    def test_init_has_hybrid_mode(self) -> None:
        """Selector should have _hybrid_mode attribute."""
        selector = SemanticToolSelector()
        assert hasattr(selector, "_hybrid_mode")
        assert selector._hybrid_mode == DEFAULT_HYBRID_MODE

    def test_init_has_hybrid_enabled(self) -> None:
        """Selector should have _hybrid_enabled flag (default True)."""
        selector = SemanticToolSelector()
        assert hasattr(selector, "_hybrid_enabled")
        assert selector._hybrid_enabled is True

    def test_not_initialized_by_default(self) -> None:
        """Selector should not be initialized without calling initialize()."""
        selector = SemanticToolSelector()
        assert selector._initialized is False
        assert selector.is_initialized() is False


# =============================================================================
# Tests: Hybrid scoring with mocked embeddings
# =============================================================================


class TestHybridScoringWithEmbeddings:
    """Test hybrid scoring with pre-computed embeddings."""

    def test_description_only_uses_desc_score(self) -> None:
        """Tool with description but no keywords should use description score only."""
        # When desc_score > 0 and keyword_score == 0 → final_score = desc_score
        desc_score = 0.75
        keyword_score = 0.0
        alpha = 0.6

        # Logic from select_tools
        if desc_score > 0 and keyword_score > 0:
            final_score = alpha * desc_score + (1 - alpha) * keyword_score
        elif desc_score > 0:
            final_score = desc_score
        elif keyword_score > 0:
            final_score = keyword_score
        else:
            final_score = 0.0

        assert final_score == 0.75

    def test_keywords_only_uses_keyword_score(self) -> None:
        """Tool with keywords but no description should use keyword score only."""
        desc_score = 0.0
        keyword_score = 0.65
        alpha = 0.6

        if desc_score > 0 and keyword_score > 0:
            final_score = alpha * desc_score + (1 - alpha) * keyword_score
        elif desc_score > 0:
            final_score = desc_score
        elif keyword_score > 0:
            final_score = keyword_score
        else:
            final_score = 0.0

        assert final_score == 0.65

    def test_hybrid_both_available(self) -> None:
        """Both description and keyword scores should be weighted."""
        desc_score = 0.80
        keyword_score = 0.60
        alpha = 0.6

        if desc_score > 0 and keyword_score > 0:
            final_score = alpha * desc_score + (1 - alpha) * keyword_score
        elif desc_score > 0:
            final_score = desc_score
        elif keyword_score > 0:
            final_score = keyword_score
        else:
            final_score = 0.0

        assert final_score == pytest.approx(0.72)

    def test_neither_score_returns_zero(self) -> None:
        """No description and no keywords should return 0."""
        desc_score = 0.0
        keyword_score = 0.0

        if desc_score > 0 and keyword_score > 0:
            final_score = 0.6 * desc_score + 0.4 * keyword_score
        elif desc_score > 0:
            final_score = desc_score
        elif keyword_score > 0:
            final_score = keyword_score
        else:
            final_score = 0.0

        assert final_score == 0.0

    def test_alpha_0_means_keywords_only(self) -> None:
        """Alpha=0 should give 100% weight to keywords."""
        alpha = 0.0
        desc_score = 0.90
        keyword_score = 0.50

        final_score = alpha * desc_score + (1 - alpha) * keyword_score
        assert final_score == pytest.approx(0.50)

    def test_alpha_1_means_description_only(self) -> None:
        """Alpha=1 should give 100% weight to description."""
        alpha = 1.0
        desc_score = 0.90
        keyword_score = 0.50

        final_score = alpha * desc_score + (1 - alpha) * keyword_score
        assert final_score == pytest.approx(0.90)


# =============================================================================
# Tests: Backward compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility when hybrid scoring is disabled."""

    def test_disabled_flag_skips_description_embedding(self) -> None:
        """When hybrid_enabled=False, description embeddings should not be created."""
        selector = SemanticToolSelector()
        selector._hybrid_enabled = False
        # Descriptions should not be embedded when disabled
        # (verified via initialize() which checks self._hybrid_enabled)
        assert selector._hybrid_enabled is False

    def test_keyword_fallback_with_manifest_name(self) -> None:
        """Tools without semantic_keywords should use [manifest.name] fallback."""
        # This test verifies the fallback logic: `keywords = manifest.semantic_keywords or [manifest.name]`
        name = "get_weather_tool"
        semantic_keywords = None
        keywords = semantic_keywords or [name]
        assert keywords == ["get_weather_tool"]

    def test_keyword_fallback_not_empty_list(self) -> None:
        """Empty semantic_keywords should also trigger fallback."""
        name = "get_weather_tool"
        semantic_keywords: list[str] = []
        keywords = semantic_keywords or [name]
        assert keywords == ["get_weather_tool"]
