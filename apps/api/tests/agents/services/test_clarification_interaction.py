"""
Unit tests for ClarificationInteraction (Phase 2.6 OPTIMPLAN).

Tests cover:
- ClarificationInteraction implementation of HitlInteractionProtocol
- Question streaming (from pre-generated questions)
- Fallback question generation
- Metadata chunk building
- Multi-language support (fr, en, es)

Created: 2025-11-26
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.domains.agents.services.hitl.interactions.clarification import (
    ClarificationInteraction,
)
from src.domains.agents.services.hitl.protocols import (
    HitlInteractionProtocol,
    HitlInteractionType,
)

# ============================================================================
# ClarificationInteraction Protocol Compliance Tests
# ============================================================================


class TestClarificationInteractionProtocol:
    """Test that ClarificationInteraction implements HitlInteractionProtocol."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    def test_implements_protocol(self, mock_question_generator):
        """Test that ClarificationInteraction satisfies Protocol."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        # Protocol check (runtime_checkable)
        assert isinstance(interaction, HitlInteractionProtocol)

    def test_interaction_type_property(self, mock_question_generator):
        """Test that interaction_type returns CLARIFICATION."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        assert interaction.interaction_type == HitlInteractionType.CLARIFICATION


# ============================================================================
# ClarificationInteraction Question Streaming Tests
# ============================================================================


class TestClarificationQuestionStreaming:
    """Test question streaming functionality."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    @pytest.fixture
    def clarification_context_with_questions(self):
        """Create context with pre-generated clarification questions."""
        return {
            "clarification_questions": [
                "Voulez-vous envoyer à UN contact ou TOUS les contacts ?",
            ],
            "semantic_issues": [
                {
                    "type": "cardinality_mismatch",
                    "description": "User said 'pour chaque' but plan does single op",
                    "severity": "high",
                }
            ],
        }

    @pytest.fixture
    def clarification_context_multiple_questions(self):
        """Create context with multiple clarification questions."""
        return {
            "clarification_questions": [
                "Voulez-vous envoyer à UN contact ou TOUS les contacts ?",
                "Faut-il inclure les contacts archivés ?",
            ],
            "semantic_issues": [
                {"type": "cardinality_mismatch", "description": "Issue 1", "severity": "high"},
                {"type": "ambiguous_intent", "description": "Issue 2", "severity": "medium"},
            ],
        }

    @pytest.fixture
    def clarification_context_no_questions(self):
        """Create context without pre-generated questions."""
        return {
            "clarification_questions": [],
            "semantic_issues": [
                {"type": "implicit_assumption", "description": "Some issue", "severity": "low"}
            ],
        }

    @pytest.mark.asyncio
    async def test_stream_single_pre_generated_question(
        self, mock_question_generator, clarification_context_with_questions
    ):
        """Test streaming a single pre-generated question."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        # Patch metrics at their actual location in metrics_agents module
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_question_ttft_seconds"
        ) as mock_ttft:
            mock_ttft.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
            with patch(
                "src.infrastructure.observability.metrics_agents.hitl_question_tokens_per_second"
            ) as mock_tps:
                mock_tps.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

                tokens = []
                async for token in interaction.generate_question_stream(
                    context=clarification_context_with_questions,
                    user_language="fr",
                ):
                    tokens.append(token)

                # Reconstruct question
                full_question = "".join(tokens).strip()
                assert "contact" in full_question.lower()
                assert "TOUS" in full_question or "UN" in full_question

    @pytest.mark.asyncio
    async def test_stream_multiple_questions_formatted(
        self, mock_question_generator, clarification_context_multiple_questions
    ):
        """Test streaming multiple questions with numbered formatting."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        # Patch metrics at their actual location in metrics_agents module
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_question_ttft_seconds"
        ) as mock_ttft:
            mock_ttft.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
            with patch(
                "src.infrastructure.observability.metrics_agents.hitl_question_tokens_per_second"
            ) as mock_tps:
                mock_tps.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

                tokens = []
                async for token in interaction.generate_question_stream(
                    context=clarification_context_multiple_questions,
                    user_language="fr",
                ):
                    tokens.append(token)

                full_question = "".join(tokens)

                # Should have header and numbered list
                assert "clarifications" in full_question.lower()
                assert "1." in full_question
                assert "2." in full_question

    @pytest.mark.asyncio
    async def test_stream_fallback_when_no_questions(
        self, mock_question_generator, clarification_context_no_questions
    ):
        """Test fallback to static question when no pre-generated questions."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        tokens = []
        async for token in interaction.generate_question_stream(
            context=clarification_context_no_questions,
            user_language="fr",
        ):
            tokens.append(token)

        full_question = "".join(tokens).strip()

        # Should use fallback message
        assert "clarification" in full_question.lower() or "préciser" in full_question.lower()

    @pytest.mark.asyncio
    async def test_stream_english_questions(
        self, mock_question_generator, clarification_context_multiple_questions
    ):
        """Test streaming questions in English."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        # Patch metrics at their actual location in metrics_agents module
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_question_ttft_seconds"
        ) as mock_ttft:
            mock_ttft.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
            with patch(
                "src.infrastructure.observability.metrics_agents.hitl_question_tokens_per_second"
            ) as mock_tps:
                mock_tps.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

                tokens = []
                async for token in interaction.generate_question_stream(
                    context=clarification_context_multiple_questions,
                    user_language="en",
                ):
                    tokens.append(token)

                full_question = "".join(tokens)

                # Should have English header
                assert "clarification" in full_question.lower()


# ============================================================================
# ClarificationInteraction Fallback Tests
# ============================================================================


class TestClarificationFallback:
    """Test fallback question functionality."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    def test_fallback_french(self, mock_question_generator):
        """Test French fallback message."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        fallback = interaction.get_fallback_question("fr")

        expected = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "fr")
        assert fallback == expected
        assert "clarification" in fallback.lower() or "préciser" in fallback.lower()

    def test_fallback_english(self, mock_question_generator):
        """Test English fallback message."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        fallback = interaction.get_fallback_question("en")

        expected = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "en")
        assert fallback == expected
        assert "clarification" in fallback.lower()

    def test_fallback_spanish(self, mock_question_generator):
        """Test Spanish fallback message."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        fallback = interaction.get_fallback_question("es")

        expected = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "es")
        assert fallback == expected
        assert "aclaraciones" in fallback.lower() or "clarifi" in fallback.lower()

    def test_fallback_unknown_language(self, mock_question_generator):
        """Test fallback for unknown language defaults to DEFAULT_LANGUAGE (fr)."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        # Use a truly unknown language (not "zh" which normalizes to "zh-CN")
        fallback = interaction.get_fallback_question("xyz")

        # Should fall back to DEFAULT_LANGUAGE (fr), not English
        # Note: _normalize_language returns DEFAULT_LANGUAGE for unknown languages
        expected = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "fr")
        assert fallback == expected


# ============================================================================
# ClarificationInteraction Metadata Tests
# ============================================================================


class TestClarificationMetadata:
    """Test metadata chunk building."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    @pytest.fixture
    def clarification_context(self):
        """Create sample clarification context."""
        return {
            "clarification_questions": [
                "Question 1?",
                "Question 2?",
            ],
            "semantic_issues": [
                {"type": "cardinality_mismatch", "description": "Issue 1", "severity": "high"},
                {"type": "ambiguous_intent", "description": "Issue 2", "severity": "medium"},
            ],
        }

    def test_build_metadata_chunk(self, mock_question_generator, clarification_context):
        """Test metadata chunk includes all required fields."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        metadata = interaction.build_metadata_chunk(
            context=clarification_context,
            message_id="clarif_123",
            conversation_id="conv-uuid-456",
        )

        # Verify required fields
        assert metadata["message_id"] == "clarif_123"
        assert metadata["conversation_id"] == "conv-uuid-456"
        assert "action_requests" in metadata
        assert metadata["count"] == 1
        assert metadata["is_plan_approval"] is False

        # Verify clarification-specific fields
        assert metadata["question_count"] == 2
        assert metadata["issue_count"] == 2
        assert "cardinality_mismatch" in metadata["issue_types"]
        assert "ambiguous_intent" in metadata["issue_types"]

    def test_build_metadata_action_requests_format(
        self, mock_question_generator, clarification_context
    ):
        """Test action_requests format in metadata."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        metadata = interaction.build_metadata_chunk(
            context=clarification_context,
            message_id="test_msg",
            conversation_id="test_conv",
        )

        action_requests = metadata["action_requests"]
        assert len(action_requests) == 1

        action = action_requests[0]
        assert action["type"] == "clarification"
        assert action["clarification_questions"] == ["Question 1?", "Question 2?"]
        assert len(action["semantic_issues"]) == 2

    def test_build_metadata_empty_context(self, mock_question_generator):
        """Test metadata with empty context."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        metadata = interaction.build_metadata_chunk(
            context={},
            message_id="empty_msg",
            conversation_id="empty_conv",
        )

        assert metadata["question_count"] == 0
        assert metadata["issue_count"] == 0
        assert metadata["issue_types"] == []


# ============================================================================
# ClarificationInteraction Format Questions Tests
# ============================================================================


class TestFormatClarificationQuestions:
    """Test question formatting logic."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    def test_format_single_question(self, mock_question_generator):
        """Test formatting single question (no header)."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        result = interaction._format_clarification_questions(
            questions=["Voulez-vous envoyer à tous ?"],
            user_language="fr",
        )

        # Single question should be returned as-is
        assert result == "Voulez-vous envoyer à tous ?"

    def test_format_multiple_questions_french(self, mock_question_generator):
        """Test formatting multiple questions in French."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        result = interaction._format_clarification_questions(
            questions=["Question 1?", "Question 2?"],
            user_language="fr",
        )

        assert "clarifications" in result.lower()
        assert "1. Question 1?" in result
        assert "2. Question 2?" in result

    def test_format_multiple_questions_english(self, mock_question_generator):
        """Test formatting multiple questions in English."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        result = interaction._format_clarification_questions(
            questions=["Question 1?", "Question 2?"],
            user_language="en",
        )

        assert "clarification" in result.lower()
        assert "1. Question 1?" in result
        assert "2. Question 2?" in result

    def test_format_multiple_questions_spanish(self, mock_question_generator):
        """Test formatting multiple questions in Spanish."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        result = interaction._format_clarification_questions(
            questions=["Pregunta 1?", "Pregunta 2?"],
            user_language="es",
        )

        assert "aclaraciones" in result.lower()
        assert "1. Pregunta 1?" in result
        assert "2. Pregunta 2?" in result

    def test_format_empty_questions(self, mock_question_generator):
        """Test formatting empty questions falls back."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        result = interaction._format_clarification_questions(
            questions=[],
            user_language="fr",
        )

        # Should return fallback
        expected = HitlMessages.get_fallback(HitlMessageType.CLARIFICATION, "fr")
        assert result == expected


# ============================================================================
# Integration Tests
# ============================================================================


class TestClarificationIntegration:
    """Integration tests for clarification flow."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_full_clarification_flow(self, mock_question_generator):
        """Test complete clarification interaction flow."""
        interaction = ClarificationInteraction(question_generator=mock_question_generator)

        context = {
            "clarification_questions": ["Voulez-vous UN ou TOUS les contacts ?"],
            "semantic_issues": [
                {"type": "cardinality_mismatch", "description": "Mismatch detected"}
            ],
        }

        # Step 1: Build metadata
        metadata = interaction.build_metadata_chunk(
            context=context,
            message_id="test_msg",
            conversation_id="test_conv",
        )
        assert metadata["is_plan_approval"] is False
        assert metadata["question_count"] == 1

        # Step 2: Stream question
        # Patch metrics at their actual location in metrics_agents module
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_question_ttft_seconds"
        ) as mock_ttft:
            mock_ttft.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
            with patch(
                "src.infrastructure.observability.metrics_agents.hitl_question_tokens_per_second"
            ) as mock_tps:
                mock_tps.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

                question = ""
                async for token in interaction.generate_question_stream(
                    context=context,
                    user_language="fr",
                ):
                    question += token

                assert "contact" in question.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
