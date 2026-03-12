"""
Unit tests for HITL Interaction Protocol, Registry, and Implementations.

Phase 1 HITL Streaming (OPTIMPLAN):
Tests cover:
- HitlInteractionType enum and conversion
- HitlInteractionProtocol structural typing
- HitlInteractionRegistry pattern
- PlanApprovalInteraction implementation
- ToolConfirmationInteraction implementation

Created: 2025-11-25
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.services.hitl.protocols import (
    HitlInteractionProtocol,
    HitlInteractionType,
)
from src.domains.agents.services.hitl.registry import HitlInteractionRegistry

# ============================================================================
# HitlInteractionType Tests
# ============================================================================


class TestHitlInteractionType:
    """Test suite for HitlInteractionType enum."""

    def test_type_values(self):
        """Test that all expected types are defined."""
        assert HitlInteractionType.PLAN_APPROVAL.value == "plan_approval"
        assert HitlInteractionType.TOOL_CONFIRMATION.value == "tool_confirmation"
        assert HitlInteractionType.CLARIFICATION.value == "clarification"
        assert HitlInteractionType.EDIT_CONFIRMATION.value == "edit_confirmation"
        assert HitlInteractionType.FOR_EACH_CONFIRMATION.value == "for_each_confirmation"

    def test_from_action_type_valid(self):
        """Test conversion from valid action_type strings."""
        assert (
            HitlInteractionType.from_action_type("plan_approval")
            == HitlInteractionType.PLAN_APPROVAL
        )
        assert (
            HitlInteractionType.from_action_type("tool_confirmation")
            == HitlInteractionType.TOOL_CONFIRMATION
        )
        assert (
            HitlInteractionType.from_action_type("clarification")
            == HitlInteractionType.CLARIFICATION
        )

    def test_from_action_type_unknown_falls_back_to_plan_approval(self):
        """Test that unknown action_type falls back to PLAN_APPROVAL."""
        assert (
            HitlInteractionType.from_action_type("unknown_type")
            == HitlInteractionType.PLAN_APPROVAL
        )
        assert HitlInteractionType.from_action_type("") == HitlInteractionType.PLAN_APPROVAL
        assert HitlInteractionType.from_action_type("invalid") == HitlInteractionType.PLAN_APPROVAL


# ============================================================================
# HitlInteractionRegistry Tests
# ============================================================================


class TestHitlInteractionRegistry:
    """Test suite for HitlInteractionRegistry."""

    def setup_method(self):
        """Clear registry before each test."""
        # Save original state
        self._original_interactions = HitlInteractionRegistry._interactions.copy()

    def teardown_method(self):
        """Restore registry after each test."""
        HitlInteractionRegistry._interactions = self._original_interactions

    def test_register_decorator(self):
        """Test that @register decorator adds class to registry."""
        # Clear for this test
        HitlInteractionRegistry.clear()

        @HitlInteractionRegistry.register(HitlInteractionType.CLARIFICATION)
        class TestInteraction:
            def __init__(self, question_generator):
                self.generator = question_generator

            @property
            def interaction_type(self):
                return HitlInteractionType.CLARIFICATION

        # Assert registration
        assert HitlInteractionRegistry.is_registered(HitlInteractionType.CLARIFICATION)
        assert HitlInteractionType.CLARIFICATION in HitlInteractionRegistry.list_registered()

    def test_get_creates_instance_with_kwargs(self):
        """Test that get() creates instance with provided kwargs."""
        # Clear for this test
        HitlInteractionRegistry.clear()

        @HitlInteractionRegistry.register(HitlInteractionType.CLARIFICATION)
        class TestInteraction:
            def __init__(self, question_generator, custom_param=None):
                self.generator = question_generator
                self.custom = custom_param

            @property
            def interaction_type(self):
                return HitlInteractionType.CLARIFICATION

        # Get instance
        mock_generator = MagicMock()
        interaction = HitlInteractionRegistry.get(
            HitlInteractionType.CLARIFICATION,
            question_generator=mock_generator,
            custom_param="test_value",
        )

        assert interaction.generator is mock_generator
        assert interaction.custom == "test_value"

    def test_get_unregistered_type_raises_keyerror(self):
        """Test that get() raises KeyError for unregistered types."""
        # Clear registry
        HitlInteractionRegistry.clear()

        with pytest.raises(KeyError) as exc_info:
            HitlInteractionRegistry.get(HitlInteractionType.EDIT_CONFIRMATION)

        assert "edit_confirmation" in str(exc_info.value)

    def test_from_action_type_creates_correct_interaction(self):
        """Test from_action_type() creates interaction based on action string."""
        # Ensure registrations exist
        # Import to trigger registration

        mock_generator = MagicMock()

        # Get by action_type string
        plan_interaction = HitlInteractionRegistry.from_action_type(
            "plan_approval",
            question_generator=mock_generator,
        )
        assert plan_interaction.interaction_type == HitlInteractionType.PLAN_APPROVAL

        tool_interaction = HitlInteractionRegistry.from_action_type(
            "tool_confirmation",
            question_generator=mock_generator,
        )
        assert tool_interaction.interaction_type == HitlInteractionType.TOOL_CONFIRMATION

    def test_from_action_type_unknown_falls_back(self):
        """Test that unknown action_type falls back to PLAN_APPROVAL."""
        # Ensure PlanApprovalInteraction is registered

        mock_generator = MagicMock()

        interaction = HitlInteractionRegistry.from_action_type(
            "unknown_type",
            question_generator=mock_generator,
        )

        # Should fall back to plan_approval
        assert interaction.interaction_type == HitlInteractionType.PLAN_APPROVAL

    def test_list_registered_returns_all_types(self):
        """Test list_registered() returns all registered types."""
        # Import to ensure registration

        registered = HitlInteractionRegistry.list_registered()

        assert HitlInteractionType.PLAN_APPROVAL in registered
        assert HitlInteractionType.TOOL_CONFIRMATION in registered


# ============================================================================
# PlanApprovalInteraction Tests
# ============================================================================


class TestPlanApprovalInteraction:
    """Test suite for PlanApprovalInteraction."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        mock = MagicMock()
        # Setup async generator for streaming
        mock.generate_plan_approval_question_stream = AsyncMock()
        return mock

    @pytest.fixture
    def plan_approval_context(self):
        """Create sample plan approval context."""
        return {
            "type": "plan_approval",
            "plan_summary": {
                "plan_id": "test-plan-123",
                "total_steps": 3,
                "total_cost_usd": 0.05,
                "hitl_steps_count": 1,
                "steps": [
                    {"step_id": 1, "tool_name": "search_contacts_tool"},
                    {"step_id": 2, "tool_name": "get_contact_details_tool"},
                    {"step_id": 3, "tool_name": "send_email_tool"},
                ],
            },
            "approval_reasons": ["Plan contains tools requiring HITL approval"],
            "strategies_triggered": ["ManifestBasedStrategy"],
        }

    def test_interaction_type_property(self, mock_question_generator):
        """Test that interaction_type returns PLAN_APPROVAL."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        interaction = PlanApprovalInteraction(question_generator=mock_question_generator)
        assert interaction.interaction_type == HitlInteractionType.PLAN_APPROVAL

    @pytest.mark.asyncio
    async def test_generate_question_stream_calls_generator(
        self, mock_question_generator, plan_approval_context
    ):
        """Test that generate_question_stream delegates to question_generator."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        # Setup mock stream - must be a function that returns an async generator
        async def mock_stream(*args, **kwargs):
            for token in ["Test", " question"]:
                yield token

        # Use side_effect for async generator functions
        mock_question_generator.generate_plan_approval_question_stream = mock_stream

        interaction = PlanApprovalInteraction(question_generator=mock_question_generator)

        # Stream tokens
        tokens = []
        async for token in interaction.generate_question_stream(
            context=plan_approval_context,
            user_language="fr",
        ):
            tokens.append(token)

        # Verify tokens were collected
        assert tokens == ["Test", " question"]

    def test_build_metadata_chunk_includes_required_fields(
        self, mock_question_generator, plan_approval_context
    ):
        """Test that build_metadata_chunk creates proper metadata."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        interaction = PlanApprovalInteraction(question_generator=mock_question_generator)

        metadata = interaction.build_metadata_chunk(
            context=plan_approval_context,
            message_id="hitl_123_abc",
            conversation_id="conv-uuid-456",
        )

        # Verify required fields
        assert metadata["message_id"] == "hitl_123_abc"
        assert metadata["conversation_id"] == "conv-uuid-456"
        assert "action_requests" in metadata
        assert metadata["count"] >= 1
        assert metadata["is_plan_approval"] is True

    def test_get_fallback_question_returns_language_specific(self, mock_question_generator):
        """Test that fallback question is language-specific."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        interaction = PlanApprovalInteraction(question_generator=mock_question_generator)

        # Test French
        fr_fallback = interaction.get_fallback_question("fr")
        assert "approbation" in fr_fallback.lower() or "valider" in fr_fallback.lower()

        # Test English
        en_fallback = interaction.get_fallback_question("en")
        assert "approval" in en_fallback.lower() or "proceed" in en_fallback.lower()

        # Test unknown falls back to default language (project default, may be fr or en)
        from src.core.i18n import DEFAULT_LANGUAGE

        unknown_fallback = interaction.get_fallback_question("xy")  # Truly unknown language
        default_fallback = interaction.get_fallback_question(DEFAULT_LANGUAGE)
        assert unknown_fallback == default_fallback


# ============================================================================
# ToolConfirmationInteraction Tests
# ============================================================================


class TestToolConfirmationInteraction:
    """Test suite for ToolConfirmationInteraction."""

    @pytest.fixture
    def mock_question_generator(self):
        """Create mock HitlQuestionGenerator."""
        mock = MagicMock()
        mock.generate_confirmation_question_stream = AsyncMock()
        return mock

    @pytest.fixture
    def tool_confirmation_context(self):
        """Create sample tool confirmation context."""
        return {
            "type": "tool_confirmation",
            "tool_name": "delete_email_tool",
            "tool_args": {
                "email_id": "msg-123",
                "permanent": True,
            },
        }

    def test_interaction_type_property(self, mock_question_generator):
        """Test that interaction_type returns TOOL_CONFIRMATION."""
        from src.domains.agents.services.hitl.interactions import (
            ToolConfirmationInteraction,
        )

        interaction = ToolConfirmationInteraction(question_generator=mock_question_generator)
        assert interaction.interaction_type == HitlInteractionType.TOOL_CONFIRMATION

    @pytest.mark.asyncio
    async def test_generate_question_stream_calls_generator(
        self, mock_question_generator, tool_confirmation_context
    ):
        """Test that generate_question_stream delegates to question_generator."""
        from src.domains.agents.services.hitl.interactions import (
            ToolConfirmationInteraction,
        )

        # Track call arguments
        call_args_captured = {}

        # Setup mock stream - must be a function that returns an async generator
        async def mock_stream(*args, **kwargs):
            nonlocal call_args_captured
            call_args_captured = kwargs
            for token in ["Supprimer", " cet ", "email", "?"]:
                yield token

        # Use direct assignment for async generator functions
        mock_question_generator.generate_confirmation_question_stream = mock_stream

        interaction = ToolConfirmationInteraction(question_generator=mock_question_generator)

        # Stream tokens
        tokens = []
        async for token in interaction.generate_question_stream(
            context=tool_confirmation_context,
            user_language="fr",
        ):
            tokens.append(token)

        # Verify delegation
        assert call_args_captured["tool_name"] == "delete_email_tool"
        assert call_args_captured["tool_args"] == {"email_id": "msg-123", "permanent": True}
        assert call_args_captured["user_language"] == "fr"
        assert tokens == ["Supprimer", " cet ", "email", "?"]

    def test_build_metadata_chunk_includes_tool_info(
        self, mock_question_generator, tool_confirmation_context
    ):
        """Test that build_metadata_chunk includes tool-specific metadata."""
        from src.domains.agents.services.hitl.interactions import (
            ToolConfirmationInteraction,
        )

        interaction = ToolConfirmationInteraction(question_generator=mock_question_generator)

        metadata = interaction.build_metadata_chunk(
            context=tool_confirmation_context,
            message_id="hitl_tool_123",
            conversation_id="conv-uuid-789",
        )

        # Verify required fields
        assert metadata["message_id"] == "hitl_tool_123"
        assert metadata["conversation_id"] == "conv-uuid-789"
        assert metadata["is_plan_approval"] is False
        assert metadata["tool_name"] == "delete_email_tool"

    def test_get_fallback_question_returns_language_specific(self, mock_question_generator):
        """Test that fallback question is language-specific."""
        from src.domains.agents.services.hitl.interactions import (
            ToolConfirmationInteraction,
        )

        interaction = ToolConfirmationInteraction(question_generator=mock_question_generator)

        # Test French
        fr_fallback = interaction.get_fallback_question("fr")
        assert "confirmation" in fr_fallback.lower() or "continuer" in fr_fallback.lower()

        # Test English
        en_fallback = interaction.get_fallback_question("en")
        assert "confirmation" in en_fallback.lower() or "proceed" in en_fallback.lower()


# ============================================================================
# Protocol Compliance Tests
# ============================================================================


class TestProtocolCompliance:
    """Test that implementations satisfy HitlInteractionProtocol."""

    def test_plan_approval_implements_protocol(self):
        """Test PlanApprovalInteraction satisfies Protocol."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        mock_generator = MagicMock()
        interaction = PlanApprovalInteraction(question_generator=mock_generator)

        # Protocol check (runtime_checkable)
        assert isinstance(interaction, HitlInteractionProtocol)

    def test_tool_confirmation_implements_protocol(self):
        """Test ToolConfirmationInteraction satisfies Protocol."""
        from src.domains.agents.services.hitl.interactions import (
            ToolConfirmationInteraction,
        )

        mock_generator = MagicMock()
        interaction = ToolConfirmationInteraction(question_generator=mock_generator)

        # Protocol check (runtime_checkable)
        assert isinstance(interaction, HitlInteractionProtocol)

    def test_custom_interaction_can_implement_protocol(self):
        """Test that custom implementations can satisfy Protocol."""

        class CustomInteraction:
            @property
            def interaction_type(self):
                return HitlInteractionType.CLARIFICATION

            async def generate_question_stream(self, context, user_language, tracker=None):
                yield "Custom question"

            def build_metadata_chunk(self, context, message_id, conversation_id):
                return {"message_id": message_id}

            def get_fallback_question(self, user_language):
                return "Fallback"

        custom = CustomInteraction()
        assert isinstance(custom, HitlInteractionProtocol)


# ============================================================================
# Integration Tests
# ============================================================================


class TestInteractionIntegration:
    """Integration tests for the full interaction flow."""

    @pytest.mark.asyncio
    async def test_full_plan_approval_flow(self):
        """Test complete plan approval interaction flow."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        # Create mock generator with real streaming behavior
        mock_generator = MagicMock()

        async def fake_stream(*args, **kwargs):
            for token in ["Ce ", "plan ", "nécessite ", "ton ", "approbation."]:
                await asyncio.sleep(0.001)  # Simulate latency
                yield token

        mock_generator.generate_plan_approval_question_stream.return_value = fake_stream()

        interaction = PlanApprovalInteraction(question_generator=mock_generator)

        context = {
            "plan_summary": {"plan_id": "test", "total_steps": 2},
            "approval_reasons": ["Test reason"],
            "strategies_triggered": ["TestStrategy"],
        }

        # Step 1: Build metadata
        metadata = interaction.build_metadata_chunk(
            context=context,
            message_id="test_msg",
            conversation_id="test_conv",
        )
        assert metadata["is_plan_approval"] is True

        # Step 2: Stream question
        question = ""
        async for token in interaction.generate_question_stream(
            context=context,
            user_language="fr",
        ):
            question += token

        assert question == "Ce plan nécessite ton approbation."

    @pytest.mark.asyncio
    async def test_registry_to_streaming_flow(self):
        """Test from registry lookup to streaming."""
        from src.domains.agents.services.hitl.interactions import PlanApprovalInteraction

        # Mock generator
        mock_generator = MagicMock()

        async def fake_stream(*args, **kwargs):
            yield "Token1"
            yield "Token2"

        mock_generator.generate_plan_approval_question_stream.return_value = fake_stream()

        # Get interaction via registry
        interaction = HitlInteractionRegistry.from_action_type(
            "plan_approval",
            question_generator=mock_generator,
        )

        # Verify type
        assert isinstance(interaction, PlanApprovalInteraction)

        # Stream
        tokens = []
        async for token in interaction.generate_question_stream(
            context={"plan_summary": {}},
            user_language="en",
        ):
            tokens.append(token)

        assert tokens == ["Token1", "Token2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
