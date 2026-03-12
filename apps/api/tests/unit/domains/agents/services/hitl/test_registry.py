"""
Unit tests for HITL Interaction Registry.

Tests the registry pattern for HITL interaction implementations including:
- Registration via decorator
- Instance creation via factory
- Lookup by interaction type and action type string

@created: 2026-02-02
@coverage: registry.py
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.hitl.protocols import (
    HitlInteractionProtocol,
    HitlInteractionType,
)
from src.domains.agents.services.hitl.registry import HitlInteractionRegistry

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean registry before and after each test."""
    # Save original state
    original_interactions = HitlInteractionRegistry._interactions.copy()

    # Clear for test
    HitlInteractionRegistry.clear()

    yield

    # Restore original state
    HitlInteractionRegistry._interactions = original_interactions


# ============================================================================
# Mock Interaction Classes
# ============================================================================


class MockPlanApprovalInteraction:
    """Mock implementation of plan approval interaction."""

    def __init__(self, question_generator=None):
        self.question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        return HitlInteractionType.PLAN_APPROVAL

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker=None,
    ) -> AsyncGenerator[str, None]:
        yield "Mock question"

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {"message_id": message_id}

    def get_fallback_question(self, user_language: str) -> str:
        return "Fallback question"


class MockClarificationInteraction:
    """Mock implementation of clarification interaction."""

    def __init__(self, question_generator=None):
        self.question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        return HitlInteractionType.CLARIFICATION

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker=None,
    ) -> AsyncGenerator[str, None]:
        yield "Clarification question"

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return {"message_id": message_id}

    def get_fallback_question(self, user_language: str) -> str:
        return "Clarification fallback"


# ============================================================================
# register Decorator Tests
# ============================================================================


class TestRegisterDecorator:
    """Tests for HitlInteractionRegistry.register decorator."""

    def test_register_single_interaction(self):
        """Test registering a single interaction class."""

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class TestInteraction:
            pass

        assert HitlInteractionRegistry.is_registered(HitlInteractionType.PLAN_APPROVAL)
        assert HitlInteractionType.PLAN_APPROVAL in HitlInteractionRegistry._interactions

    def test_register_multiple_interactions(self):
        """Test registering multiple interaction classes."""

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class PlanApproval:
            pass

        @HitlInteractionRegistry.register(HitlInteractionType.CLARIFICATION)
        class Clarification:
            pass

        assert HitlInteractionRegistry.is_registered(HitlInteractionType.PLAN_APPROVAL)
        assert HitlInteractionRegistry.is_registered(HitlInteractionType.CLARIFICATION)

    def test_register_returns_original_class(self):
        """Test decorator returns the original class unchanged."""

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class OriginalClass:
            custom_attr = "test"

        assert OriginalClass.custom_attr == "test"

    @patch("src.domains.agents.services.hitl.registry.logger")
    def test_register_warns_on_duplicate(self, mock_logger):
        """Test warning is logged when registering duplicate."""

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class FirstClass:
            pass

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class SecondClass:
            pass

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "hitl_interaction_already_registered"

    def test_register_allows_override_for_testing(self):
        """Test duplicate registration allows override (for testing)."""

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class FirstClass:
            value = "first"

        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class SecondClass:
            value = "second"

        # Should use the second (latest) registration
        registered = HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL]
        assert registered.value == "second"


# ============================================================================
# get Method Tests
# ============================================================================


class TestGetMethod:
    """Tests for HitlInteractionRegistry.get method."""

    def test_get_registered_interaction(self):
        """Test getting a registered interaction."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        interaction = HitlInteractionRegistry.get(HitlInteractionType.PLAN_APPROVAL)

        assert isinstance(interaction, MockPlanApprovalInteraction)

    def test_get_with_kwargs(self):
        """Test getting interaction with constructor kwargs."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        mock_generator = MagicMock()
        interaction = HitlInteractionRegistry.get(
            HitlInteractionType.PLAN_APPROVAL,
            question_generator=mock_generator,
        )

        assert interaction.question_generator is mock_generator

    def test_get_unregistered_raises_key_error(self):
        """Test getting unregistered interaction raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            HitlInteractionRegistry.get(HitlInteractionType.DRAFT_CRITIQUE)

        assert "draft_critique" in str(exc_info.value).lower()
        assert "No interaction registered" in str(exc_info.value)

    @patch("src.domains.agents.services.hitl.registry.logger")
    def test_get_logs_error_on_not_found(self, mock_logger):
        """Test error is logged when interaction not found."""
        try:
            HitlInteractionRegistry.get(HitlInteractionType.DRAFT_CRITIQUE)
        except KeyError:
            pass

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert call_args[0][0] == "hitl_interaction_not_registered"

    def test_get_creates_new_instance_each_time(self):
        """Test each get() call creates a new instance."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        instance1 = HitlInteractionRegistry.get(HitlInteractionType.PLAN_APPROVAL)
        instance2 = HitlInteractionRegistry.get(HitlInteractionType.PLAN_APPROVAL)

        assert instance1 is not instance2


# ============================================================================
# from_action_type Method Tests
# ============================================================================


class TestFromActionType:
    """Tests for HitlInteractionRegistry.from_action_type method."""

    def test_from_action_type_valid_string(self):
        """Test from_action_type with valid action type string."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        interaction = HitlInteractionRegistry.from_action_type("plan_approval")

        assert isinstance(interaction, MockPlanApprovalInteraction)

    def test_from_action_type_clarification(self):
        """Test from_action_type with clarification type."""
        HitlInteractionRegistry._interactions[HitlInteractionType.CLARIFICATION] = (
            MockClarificationInteraction
        )

        interaction = HitlInteractionRegistry.from_action_type("clarification")

        assert isinstance(interaction, MockClarificationInteraction)

    def test_from_action_type_with_kwargs(self):
        """Test from_action_type passes kwargs to constructor."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        mock_generator = MagicMock()
        interaction = HitlInteractionRegistry.from_action_type(
            "plan_approval",
            question_generator=mock_generator,
        )

        assert interaction.question_generator is mock_generator

    def test_from_action_type_unknown_falls_back_to_plan_approval(self):
        """Test unknown action_type falls back to PLAN_APPROVAL.

        Note: HitlInteractionType.from_action_type silently falls back to
        PLAN_APPROVAL without raising ValueError, so the registry method
        doesn't log a warning (the enum handles the fallback internally).
        """
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        interaction = HitlInteractionRegistry.from_action_type("unknown_type")

        assert isinstance(interaction, MockPlanApprovalInteraction)
        # Verify it's actually the PLAN_APPROVAL interaction
        assert interaction.interaction_type == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_all_valid_types(self):
        """Test from_action_type with all valid HitlInteractionType values."""
        # Register mock for all types
        for interaction_type in HitlInteractionType:
            HitlInteractionRegistry._interactions[interaction_type] = MockPlanApprovalInteraction

        # Test each type
        for interaction_type in HitlInteractionType:
            interaction = HitlInteractionRegistry.from_action_type(interaction_type.value)
            assert interaction is not None


# ============================================================================
# list_registered Method Tests
# ============================================================================


class TestListRegistered:
    """Tests for HitlInteractionRegistry.list_registered method."""

    def test_list_registered_empty(self):
        """Test list_registered with no registrations."""
        result = HitlInteractionRegistry.list_registered()
        assert result == []

    def test_list_registered_single(self):
        """Test list_registered with single registration."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        result = HitlInteractionRegistry.list_registered()

        assert len(result) == 1
        assert HitlInteractionType.PLAN_APPROVAL in result

    def test_list_registered_multiple(self):
        """Test list_registered with multiple registrations."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )
        HitlInteractionRegistry._interactions[HitlInteractionType.CLARIFICATION] = (
            MockClarificationInteraction
        )

        result = HitlInteractionRegistry.list_registered()

        assert len(result) == 2
        assert HitlInteractionType.PLAN_APPROVAL in result
        assert HitlInteractionType.CLARIFICATION in result


# ============================================================================
# is_registered Method Tests
# ============================================================================


class TestIsRegistered:
    """Tests for HitlInteractionRegistry.is_registered method."""

    def test_is_registered_true(self):
        """Test is_registered returns True for registered type."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        result = HitlInteractionRegistry.is_registered(HitlInteractionType.PLAN_APPROVAL)

        assert result is True

    def test_is_registered_false(self):
        """Test is_registered returns False for unregistered type."""
        result = HitlInteractionRegistry.is_registered(HitlInteractionType.DRAFT_CRITIQUE)

        assert result is False


# ============================================================================
# clear Method Tests
# ============================================================================


class TestClearMethod:
    """Tests for HitlInteractionRegistry.clear method."""

    def test_clear_removes_all_registrations(self):
        """Test clear removes all registrations."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )
        HitlInteractionRegistry._interactions[HitlInteractionType.CLARIFICATION] = (
            MockClarificationInteraction
        )

        HitlInteractionRegistry.clear()

        assert len(HitlInteractionRegistry._interactions) == 0
        assert HitlInteractionRegistry.list_registered() == []

    @patch("src.domains.agents.services.hitl.registry.logger")
    def test_clear_logs_warning(self, mock_logger):
        """Test clear logs warning (for debugging)."""
        HitlInteractionRegistry.clear()

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "hitl_interaction_registry_cleared"


# ============================================================================
# Integration Tests
# ============================================================================


class TestRegistryIntegration:
    """Integration tests for registry pattern."""

    def test_full_registration_and_retrieval_workflow(self):
        """Test complete registration and retrieval workflow."""

        # 1. Register interaction via decorator
        @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        class MyPlanApproval:
            def __init__(self, question_generator=None, custom_param=None):
                self.question_generator = question_generator
                self.custom_param = custom_param

            @property
            def interaction_type(self):
                return HitlInteractionType.PLAN_APPROVAL

        # 2. Verify registration
        assert HitlInteractionRegistry.is_registered(HitlInteractionType.PLAN_APPROVAL)
        assert HitlInteractionType.PLAN_APPROVAL in HitlInteractionRegistry.list_registered()

        # 3. Retrieve instance with kwargs
        mock_gen = MagicMock()
        interaction = HitlInteractionRegistry.get(
            HitlInteractionType.PLAN_APPROVAL,
            question_generator=mock_gen,
            custom_param="test_value",
        )

        # 4. Verify instance
        assert interaction.question_generator is mock_gen
        assert interaction.custom_param == "test_value"
        assert interaction.interaction_type == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_in_streaming_service_context(self):
        """Test from_action_type as used in StreamingService."""
        # Register mock
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        # Simulate StreamingService._handle_hitl_interrupt
        first_action = {"type": "plan_approval", "name": "some_tool"}
        action_type = first_action.get("type", "unknown")

        mock_generator = MagicMock()
        interaction = HitlInteractionRegistry.from_action_type(
            action_type,
            question_generator=mock_generator,
        )

        assert isinstance(interaction, MockPlanApprovalInteraction)
        assert interaction.question_generator is mock_generator

    def test_protocol_compliance(self):
        """Test registered class can be checked against protocol."""
        HitlInteractionRegistry._interactions[HitlInteractionType.PLAN_APPROVAL] = (
            MockPlanApprovalInteraction
        )

        interaction = HitlInteractionRegistry.get(HitlInteractionType.PLAN_APPROVAL)

        # Should satisfy runtime protocol check
        assert isinstance(interaction, HitlInteractionProtocol)
