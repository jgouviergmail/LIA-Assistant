"""
Unit tests for domains/interests/services/content_sources/content_generator.py.

Tests content generation orchestration with diversity retry mechanism.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import INTEREST_CONTENT_DIVERSITY_ANGLES
from src.domains.interests.services.content_sources.base import (
    ContentGenerationContext,
    ContentResult,
)
from src.domains.interests.services.content_sources.content_generator import (
    InterestContentGenerator,
)


def _make_context(**overrides) -> ContentGenerationContext:
    """Create a ContentGenerationContext with defaults."""
    defaults = {
        "interest_id": "int-001",
        "topic": "intelligence artificielle",
        "category": "technology",
        "user_id": "user-001",
        "user_language": "fr",
        "recent_notification_embeddings": [[0.1] * 384],
    }
    defaults.update(overrides)
    return ContentGenerationContext(**defaults)


def _make_content(source: str = "brave", content: str = "Test content") -> ContentResult:
    """Create a ContentResult with defaults."""
    return ContentResult(
        content=content,
        source=source,
        raw_content=content,
        embedding=[0.5] * 384,
    )


@pytest.mark.unit
class TestContentGeneratorGenerate:
    """Tests for InterestContentGenerator.generate()."""

    @pytest.mark.asyncio
    async def test_success_first_source_no_retry(self):
        """Test successful generation from first source — no retry needed."""
        generator = InterestContentGenerator()
        context = _make_context()
        content = _make_content("brave")

        generator._try_source = AsyncMock(return_value=content)
        generator._is_duplicate = MagicMock(return_value=False)
        generator._get_shuffled_primary_sources = MagicMock(return_value=[generator._brave_source])

        result = await generator.generate(context)

        assert result.success is True
        assert result.source_used == "brave"
        assert result.dedup_skipped is False

    @pytest.mark.asyncio
    async def test_all_duplicate_then_retry_succeeds(self):
        """Test all sources duplicate → retry with angle succeeds."""
        generator = InterestContentGenerator()
        context = _make_context()

        # First call: primary=duplicate, LLM=duplicate → _try_all_sources returns None
        # Second call (retry): primary=non-duplicate → _try_all_sources returns success
        content_ok = _make_content("brave", "Angled content")

        call_count = 0

        async def mock_try_all_sources(ctx, sources_tried, retry_label=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                sources_tried.extend(["brave", "perplexity", "llm_reflection"])
                return None  # all duplicate
            else:
                sources_tried.append(f"brave(retry:{retry_label})")
                from src.domains.interests.services.content_sources.content_generator import (
                    GenerationResult,
                )

                return GenerationResult(
                    success=True,
                    content_result=content_ok,
                    sources_tried=sources_tried,
                    source_used="brave",
                )

        generator._try_all_sources = mock_try_all_sources

        result = await generator.generate(context)

        assert result.success is True
        assert result.source_used == "brave"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_duplicate_retry_also_fails(self):
        """Test all sources duplicate → retry also duplicate → dedup_skipped."""
        generator = InterestContentGenerator()
        context = _make_context()

        async def mock_try_all_sources(ctx, sources_tried, retry_label=None):
            sources_tried.append("brave")
            return None  # always duplicate

        generator._try_all_sources = mock_try_all_sources

        result = await generator.generate(context)

        assert result.success is False
        assert result.dedup_skipped is True
        assert "diversity retry" in result.error

    @pytest.mark.asyncio
    async def test_source_failure_no_retry(self):
        """Test no source produces content → GenerationResult(success=False), no retry."""
        generator = InterestContentGenerator()
        context = _make_context()

        from src.domains.interests.services.content_sources.content_generator import (
            GenerationResult,
        )

        async def mock_try_all_sources(ctx, sources_tried, retry_label=None):
            sources_tried.extend(["brave", "perplexity", "llm_reflection"])
            return GenerationResult(
                success=False,
                sources_tried=sources_tried,
                error="All content sources failed to generate content",
            )

        generator._try_all_sources = mock_try_all_sources

        result = await generator.generate(context)

        assert result.success is False
        assert result.dedup_skipped is False
        assert "All content sources failed" in result.error

    @pytest.mark.asyncio
    async def test_mixed_duplicate_and_failure_retries(self):
        """Test Brave=dup + Perplexity=None + LLM=None → retry triggered."""
        generator = InterestContentGenerator()
        context = _make_context()

        content_dup = _make_content("brave", "Duplicate content")
        content_ok = _make_content("brave", "Fresh angled content")

        # Simulate: first pass → had_duplicate=True, LLM=None → return None
        # Second pass (retry) → brave returns non-dup content
        call_count = 0

        async def mock_try_source(source, ctx):
            nonlocal call_count
            if source.source_name == "brave" and call_count == 0:
                return content_dup
            if source.source_name == "brave" and call_count == 1:
                return content_ok
            return None

        generator._try_source = mock_try_source

        dup_count = 0

        def mock_is_duplicate(content, embeddings):
            nonlocal dup_count
            # First brave call is duplicate, second (retry) is not
            if content.content == "Duplicate content":
                dup_count += 1
                return True
            return False

        generator._is_duplicate = mock_is_duplicate
        generator._get_shuffled_primary_sources = MagicMock(return_value=[generator._brave_source])

        # We need to track which call to _try_all_sources this is
        tas_count = 0

        async def counting_try_all(ctx, sources_tried, retry_label=None):
            nonlocal tas_count, call_count
            call_count = tas_count
            tas_count += 1
            return await InterestContentGenerator._try_all_sources(
                generator, ctx, sources_tried, retry_label
            )

        generator._try_all_sources = counting_try_all

        result = await generator.generate(context)

        assert result.success is True
        assert dup_count >= 1


@pytest.mark.unit
class TestPickDiversityAngle:
    """Tests for _pick_diversity_angle."""

    def test_known_language_returns_angle(self):
        """Test that a known language returns a valid angle."""
        angle = InterestContentGenerator._pick_diversity_angle("fr")
        assert angle is not None
        assert angle in INTEREST_CONTENT_DIVERSITY_ANGLES["fr"]

    def test_locale_format_supported(self):
        """Test that locale format (fr-FR) is handled."""
        angle = InterestContentGenerator._pick_diversity_angle("fr-FR")
        assert angle is not None
        assert angle in INTEREST_CONTENT_DIVERSITY_ANGLES["fr"]

    def test_unknown_language_falls_back_to_english(self):
        """Test that unknown language falls back to English angles."""
        angle = InterestContentGenerator._pick_diversity_angle("ja")
        assert angle is not None
        assert angle in INTEREST_CONTENT_DIVERSITY_ANGLES["en"]

    def test_all_supported_languages_have_angles(self):
        """Test that all supported languages return angles."""
        for lang in ["fr", "en", "es", "de", "it", "zh"]:
            angle = InterestContentGenerator._pick_diversity_angle(lang)
            assert angle is not None, f"No angle for {lang}"


@pytest.mark.unit
class TestApplyAngleToTopic:
    """Tests for _apply_angle_to_topic."""

    def test_basic_format(self):
        """Test basic angle application."""
        result = InterestContentGenerator._apply_angle_to_topic(
            "Films de SF", "perspectives futures"
        )
        assert result == "Films de SF : perspectives futures"

    def test_preserves_original_topic(self):
        """Test that original topic is preserved in output."""
        topic = "Intelligence artificielle"
        angle = "controverses et débats"
        result = InterestContentGenerator._apply_angle_to_topic(topic, angle)
        assert result.startswith(topic)
        assert angle in result


@pytest.mark.unit
class TestTryAllSources:
    """Tests for _try_all_sources return semantics."""

    @pytest.mark.asyncio
    async def test_returns_success_on_non_duplicate(self):
        """Test returns GenerationResult(success=True) when non-dup content found."""
        generator = InterestContentGenerator()
        context = _make_context()
        content = _make_content("brave")

        generator._try_source = AsyncMock(return_value=content)
        generator._is_duplicate = MagicMock(return_value=False)
        generator._get_shuffled_primary_sources = MagicMock(return_value=[generator._brave_source])

        sources_tried: list[str] = []
        result = await generator._try_all_sources(context, sources_tried)

        assert result is not None
        assert result.success is True
        assert result.source_used == "brave"

    @pytest.mark.asyncio
    async def test_returns_none_when_all_duplicate(self):
        """Test returns None when all sources produce duplicate content."""
        generator = InterestContentGenerator()
        context = _make_context()
        content = _make_content("brave")

        generator._try_source = AsyncMock(return_value=content)
        generator._is_duplicate = MagicMock(return_value=True)
        generator._get_shuffled_primary_sources = MagicMock(return_value=[generator._brave_source])

        sources_tried: list[str] = []
        result = await generator._try_all_sources(context, sources_tried)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_failure_when_no_content_generated(self):
        """Test returns GenerationResult(success=False) when no source produces content."""
        generator = InterestContentGenerator()
        context = _make_context(recent_notification_embeddings=[])

        generator._try_source = AsyncMock(return_value=None)
        generator._get_shuffled_primary_sources = MagicMock(return_value=[generator._brave_source])

        sources_tried: list[str] = []
        result = await generator._try_all_sources(context, sources_tried)

        assert result is not None
        assert result.success is False
        assert "All content sources failed" in result.error
