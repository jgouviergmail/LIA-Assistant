"""
Tests for ForEachConfirmationInteraction.

Tests the HITL interaction for FOR_EACH bulk operations.
"""

import pytest

from src.core.i18n_hitl import HitlMessages, HitlMessageType


class TestForEachConfirmationTranslations:
    """Tests for FOR_EACH confirmation translations."""

    def test_get_translations_french(self) -> None:
        """Test French translations are complete."""
        translations = HitlMessages.get_for_each_confirm_translations("fr")

        assert "title" in translations
        assert "operation_prefix" in translations
        assert "items_suffix" in translations
        assert "confirm_question" in translations
        assert "mutation_send" in translations
        assert "mutation_create" in translations
        assert "mutation_update" in translations
        assert "mutation_delete" in translations
        assert "mutation_default" in translations

        # Verify French content
        assert translations["title"] == "Confirmation d'opération en masse"
        assert translations["mutation_send"] == "envoyer"

    def test_get_translations_english(self) -> None:
        """Test English translations are complete."""
        translations = HitlMessages.get_for_each_confirm_translations("en")

        assert translations["title"] == "Bulk Operation Confirmation"
        assert translations["mutation_send"] == "send"
        assert translations["confirm_question"] == "Do you want to continue?"

    def test_get_translations_fallback_to_default(self) -> None:
        """Test fallback to default language (French) for unknown languages."""
        translations = HitlMessages.get_for_each_confirm_translations("xx-unknown")

        # Should fall back to French (DEFAULT_LANGUAGE in settings)
        assert translations["title"] == "Confirmation d'opération en masse"

    def test_all_supported_languages(self) -> None:
        """Test all supported languages have translations."""
        languages = ["fr", "en", "es", "de", "it", "zh-CN"]

        for lang in languages:
            translations = HitlMessages.get_for_each_confirm_translations(lang)
            assert "title" in translations, f"Missing title for {lang}"
            assert "mutation_send" in translations, f"Missing mutation_send for {lang}"

    def test_all_supported_languages_have_the_singular_suffix(self) -> None:
        """A count of one item must not read as a plural ("1 éléments").

        zh-CN has no plural per CLDR — the value is duplicated anyway so the
        parity stays mechanical (same convention as the frontend `_one` keys).
        """
        languages = ["fr", "en", "es", "de", "it", "zh-CN"]

        for lang in languages:
            translations = HitlMessages.get_for_each_confirm_translations(lang)
            assert "items_suffix_one" in translations, f"Missing items_suffix_one for {lang}"


class TestForEachConfirmationFallback:
    """Tests for FOR_EACH confirmation fallback messages."""

    def test_fallback_message_french(self) -> None:
        """Test fallback message in French."""
        fallback = HitlMessages.get_fallback(HitlMessageType.FOR_EACH_CONFIRMATION, "fr")
        assert "éléments" in fallback.lower() or "action" in fallback.lower()

    def test_fallback_message_english(self) -> None:
        """Test fallback message in English."""
        fallback = HitlMessages.get_fallback(HitlMessageType.FOR_EACH_CONFIRMATION, "en")
        assert "items" in fallback.lower() or "action" in fallback.lower()


class TestForEachConfirmationInteractionBuildMessage:
    """Tests for ForEachConfirmationInteraction message building."""

    @pytest.fixture
    def interaction(self):
        """Create a ForEachConfirmationInteraction instance."""
        # We need to create a mock question generator
        from unittest.mock import Mock

        from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
            ForEachConfirmationInteraction,
        )

        mock_generator = Mock()
        return ForEachConfirmationInteraction(question_generator=mock_generator)

    def test_build_confirmation_message_single_step(self, interaction) -> None:
        """Test building confirmation message with single step."""
        message = interaction._build_confirmation_message(
            steps=[{"tool_name": "send_email_tool", "for_each_max": 5}],
            total_affected=5,
            user_language="en",
        )

        assert "Bulk Operation Confirmation" in message
        assert "5" in message
        assert "send" in message.lower()

    def test_build_confirmation_message_multiple_steps(self, interaction) -> None:
        """Test building confirmation message with multiple steps."""
        message = interaction._build_confirmation_message(
            steps=[
                {"tool_name": "send_email_tool", "for_each_max": 5},
                {"tool_name": "create_event_tool", "for_each_max": 3},
            ],
            total_affected=8,
            user_language="fr",
        )

        assert "Confirmation" in message
        assert "8" in message
        assert "Operations" in message or "Opérations" in message

    def test_one_item_reads_in_the_singular_fr(self, interaction) -> None:
        """Prod 2026-08-17: the card read "Cette action va envoyer **1** éléments"."""
        message = interaction._build_confirmation_message(
            steps=[{"tool_name": "send_peer_message_tool", "for_each_max": 10}],
            total_affected=1,
            user_language="fr",
        )

        assert "**1** élément." in message
        assert "**1** éléments" not in message

    def test_one_item_reads_in_the_singular_en(self, interaction) -> None:
        message = interaction._build_confirmation_message(
            steps=[{"tool_name": "send_peer_message_tool", "for_each_max": 10}],
            total_affected=1,
            user_language="en",
        )

        assert "**1** item." in message
        assert "**1** items" not in message

    def test_two_items_keep_the_plural(self, interaction) -> None:
        message = interaction._build_confirmation_message(
            steps=[{"tool_name": "send_email_tool", "for_each_max": 5}],
            total_affected=2,
            user_language="fr",
        )

        assert "**2** éléments." in message

    def test_per_step_lines_prefer_the_real_count(self, interaction) -> None:
        """The operations list must state the measured count, not for_each_max.

        ``item_count`` is stamped on each step by the orchestrator once the
        providers ran (ADR-185: a count shown to the user is a claim — exact,
        or absent). Steps that never got a measurement keep for_each_max.
        """
        message = interaction._build_confirmation_message(
            steps=[
                {"tool_name": "send_email_tool", "for_each_max": 10, "item_count": 1},
                {"tool_name": "create_event_tool", "for_each_max": 3},
            ],
            total_affected=4,
            user_language="en",
        )

        assert "send_email_tool: 1 item\n" in message
        assert "create_event_tool: 3 items\n" in message

    def test_detect_mutation_type_send(self, interaction) -> None:
        """Test mutation type detection for send operations."""
        mutation = interaction._detect_mutation_type(
            steps=[{"tool_name": "send_email_tool"}],
            user_language="en",
        )
        assert mutation == "send"

    def test_detect_mutation_type_create(self, interaction) -> None:
        """Test mutation type detection for create operations."""
        mutation = interaction._detect_mutation_type(
            steps=[{"tool_name": "create_event_tool"}],
            user_language="en",
        )
        assert mutation == "create"

    def test_detect_mutation_type_delete(self, interaction) -> None:
        """Test mutation type detection for delete operations."""
        mutation = interaction._detect_mutation_type(
            steps=[{"tool_name": "delete_contact_tool"}],
            user_language="en",
        )
        assert mutation == "delete"

    def test_detect_mutation_type_unknown(self, interaction) -> None:
        """Test mutation type detection for unknown operations."""
        mutation = interaction._detect_mutation_type(
            steps=[{"tool_name": "get_contacts_tool"}],
            user_language="en",
        )
        assert mutation == "affect"  # Default

    def test_build_metadata_chunk(self, interaction) -> None:
        """Test building metadata chunk for HITL response."""
        context = {
            "steps": [{"tool_name": "send_email_tool", "for_each_max": 10}],
            "total_affected": 10,
            "plan_id": "test_plan_123",
        }

        metadata = interaction.build_metadata_chunk(
            context=context,
            message_id="msg_123",
            conversation_id="conv_456",
            registry_ids=["contact_1", "contact_2"],
        )

        assert metadata["message_id"] == "msg_123"
        assert metadata["conversation_id"] == "conv_456"
        assert metadata["total_affected"] == 10
        assert metadata["plan_id"] == "test_plan_123"
        assert metadata["severity"] == "warning"
        assert len(metadata["action_requests"]) == 1
        assert metadata["action_requests"][0]["type"] == "for_each_confirmation"


class TestForEachConfirmationInteractionStream:
    """Tests for ForEachConfirmationInteraction streaming."""

    @pytest.fixture
    def interaction(self):
        """Create a ForEachConfirmationInteraction instance."""
        from unittest.mock import Mock

        from src.domains.agents.services.hitl.interactions.for_each_confirmation import (
            ForEachConfirmationInteraction,
        )

        mock_generator = Mock()
        return ForEachConfirmationInteraction(question_generator=mock_generator)

    @pytest.mark.asyncio
    async def test_generate_question_stream(self, interaction) -> None:
        """Test streaming question generation."""
        context = {
            "steps": [{"tool_name": "send_email_tool", "for_each_max": 5}],
            "total_affected": 5,
            "plan_id": "test_plan",
        }

        tokens = []
        async for token in interaction.generate_question_stream(
            context=context,
            user_language="en",
        ):
            tokens.append(token)

        # Should have multiple tokens (word by word)
        assert len(tokens) > 0

        # Reconstruct message
        message = "".join(tokens)
        assert "Bulk Operation Confirmation" in message
        assert "5" in message

    @pytest.mark.asyncio
    async def test_generate_question_stream_french(self, interaction) -> None:
        """Test streaming question generation in French."""
        context = {
            "steps": [{"tool_name": "create_event_tool", "for_each_max": 3}],
            "total_affected": 3,
            "plan_id": "test_plan_fr",
        }

        tokens = []
        async for token in interaction.generate_question_stream(
            context=context,
            user_language="fr",
        ):
            tokens.append(token)

        message = "".join(tokens)
        assert "Confirmation" in message
        assert "3" in message
