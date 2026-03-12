"""
Unit tests for HITL Protocols.

Tests the protocol definitions and HitlInteractionType enum.

@created: 2026-02-02
@coverage: protocols.py
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from src.domains.agents.services.hitl.protocols import (
    HitlInteractionProtocol,
    HitlInteractionType,
)

# ============================================================================
# HitlInteractionType Enum Tests
# ============================================================================


class TestHitlInteractionTypeEnum:
    """Tests for HitlInteractionType enumeration."""

    def test_all_interaction_types_exist(self):
        """Test all expected interaction types exist."""
        assert HitlInteractionType.PLAN_APPROVAL == "plan_approval"
        assert HitlInteractionType.TOOL_CONFIRMATION == "tool_confirmation"
        assert HitlInteractionType.CLARIFICATION == "clarification"
        assert HitlInteractionType.EDIT_CONFIRMATION == "edit_confirmation"
        assert HitlInteractionType.DRAFT_CRITIQUE == "draft_critique"
        assert HitlInteractionType.ENTITY_DISAMBIGUATION == "entity_disambiguation"
        assert HitlInteractionType.DESTRUCTIVE_CONFIRM == "destructive_confirm"
        assert HitlInteractionType.FOR_EACH_CONFIRMATION == "for_each_confirmation"

    def test_interaction_type_is_str_enum(self):
        """Test HitlInteractionType inherits from str."""
        assert isinstance(HitlInteractionType.PLAN_APPROVAL, str)
        assert HitlInteractionType.PLAN_APPROVAL == "plan_approval"

    def test_interaction_type_from_string(self):
        """Test creating interaction type from string value."""
        assert HitlInteractionType("plan_approval") == HitlInteractionType.PLAN_APPROVAL
        assert HitlInteractionType("clarification") == HitlInteractionType.CLARIFICATION
        assert HitlInteractionType("draft_critique") == HitlInteractionType.DRAFT_CRITIQUE

    def test_invalid_string_raises_value_error(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            HitlInteractionType("invalid_type")


# ============================================================================
# from_action_type Class Method Tests
# ============================================================================


class TestFromActionType:
    """Tests for HitlInteractionType.from_action_type class method."""

    def test_from_action_type_plan_approval(self):
        """Test from_action_type with plan_approval."""
        result = HitlInteractionType.from_action_type("plan_approval")
        assert result == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_tool_confirmation(self):
        """Test from_action_type with tool_confirmation."""
        result = HitlInteractionType.from_action_type("tool_confirmation")
        assert result == HitlInteractionType.TOOL_CONFIRMATION

    def test_from_action_type_clarification(self):
        """Test from_action_type with clarification."""
        result = HitlInteractionType.from_action_type("clarification")
        assert result == HitlInteractionType.CLARIFICATION

    def test_from_action_type_edit_confirmation(self):
        """Test from_action_type with edit_confirmation."""
        result = HitlInteractionType.from_action_type("edit_confirmation")
        assert result == HitlInteractionType.EDIT_CONFIRMATION

    def test_from_action_type_draft_critique(self):
        """Test from_action_type with draft_critique."""
        result = HitlInteractionType.from_action_type("draft_critique")
        assert result == HitlInteractionType.DRAFT_CRITIQUE

    def test_from_action_type_entity_disambiguation(self):
        """Test from_action_type with entity_disambiguation."""
        result = HitlInteractionType.from_action_type("entity_disambiguation")
        assert result == HitlInteractionType.ENTITY_DISAMBIGUATION

    def test_from_action_type_destructive_confirm(self):
        """Test from_action_type with destructive_confirm."""
        result = HitlInteractionType.from_action_type("destructive_confirm")
        assert result == HitlInteractionType.DESTRUCTIVE_CONFIRM

    def test_from_action_type_for_each_confirmation(self):
        """Test from_action_type with for_each_confirmation."""
        result = HitlInteractionType.from_action_type("for_each_confirmation")
        assert result == HitlInteractionType.FOR_EACH_CONFIRMATION

    def test_from_action_type_unknown_falls_back(self):
        """Test from_action_type with unknown type falls back to PLAN_APPROVAL."""
        result = HitlInteractionType.from_action_type("unknown_type")
        assert result == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_empty_string_falls_back(self):
        """Test from_action_type with empty string falls back."""
        result = HitlInteractionType.from_action_type("")
        assert result == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_none_like_falls_back(self):
        """Test from_action_type with various invalid values falls back."""
        result = HitlInteractionType.from_action_type("None")
        assert result == HitlInteractionType.PLAN_APPROVAL

    def test_from_action_type_case_sensitive(self):
        """Test from_action_type is case sensitive (uppercase fails)."""
        # Uppercase should fall back
        result = HitlInteractionType.from_action_type("PLAN_APPROVAL")
        assert result == HitlInteractionType.PLAN_APPROVAL  # Falls back, not direct match


# ============================================================================
# HitlInteractionProtocol Tests
# ============================================================================


class TestHitlInteractionProtocol:
    """Tests for HitlInteractionProtocol definition."""

    def test_protocol_is_runtime_checkable(self):
        """Test protocol can be used with isinstance."""

        # Create a class that implements the protocol
        class ValidImplementation:
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
                yield "Test"

            def build_metadata_chunk(
                self,
                context: dict[str, Any],
                message_id: str,
                conversation_id: str,
                registry_ids: list[str] | None = None,
            ) -> dict[str, Any]:
                return {}

            def get_fallback_question(self, user_language: str) -> str:
                return "Fallback"

        impl = ValidImplementation()
        assert isinstance(impl, HitlInteractionProtocol)

    def test_protocol_rejects_invalid_implementation(self):
        """Test protocol rejects class missing required methods."""

        class InvalidImplementation:
            # Missing all protocol methods
            pass

        impl = InvalidImplementation()
        assert not isinstance(impl, HitlInteractionProtocol)

    def test_protocol_rejects_partial_implementation(self):
        """Test protocol rejects class with partial implementation."""

        class PartialImplementation:
            @property
            def interaction_type(self) -> HitlInteractionType:
                return HitlInteractionType.PLAN_APPROVAL

            # Missing generate_question_stream, build_metadata_chunk, get_fallback_question

        impl = PartialImplementation()
        assert not isinstance(impl, HitlInteractionProtocol)


# ============================================================================
# Protocol Method Signature Tests
# ============================================================================


class TestProtocolMethodSignatures:
    """Tests for protocol method signatures (documentation verification)."""

    def test_generate_question_stream_signature(self):
        """Test generate_question_stream expected signature."""
        # Verify the protocol has the expected method
        assert hasattr(HitlInteractionProtocol, "generate_question_stream")

        # Verify it's defined in protocol
        method = HitlInteractionProtocol.generate_question_stream
        assert callable(method)

    def test_build_metadata_chunk_signature(self):
        """Test build_metadata_chunk expected signature."""
        assert hasattr(HitlInteractionProtocol, "build_metadata_chunk")

    def test_get_fallback_question_signature(self):
        """Test get_fallback_question expected signature."""
        assert hasattr(HitlInteractionProtocol, "get_fallback_question")

    def test_interaction_type_property_signature(self):
        """Test interaction_type property expected signature."""
        assert hasattr(HitlInteractionProtocol, "interaction_type")


# ============================================================================
# Integration Tests
# ============================================================================


class TestProtocolIntegration:
    """Integration tests for protocols."""

    def test_all_interaction_types_have_values(self):
        """Test all interaction types have string values."""
        for interaction_type in HitlInteractionType:
            assert isinstance(interaction_type.value, str)
            assert len(interaction_type.value) > 0

    def test_from_action_type_covers_all_types(self):
        """Test from_action_type can process all defined types."""
        for interaction_type in HitlInteractionType:
            result = HitlInteractionType.from_action_type(interaction_type.value)
            assert result == interaction_type

    def test_interaction_type_values_are_unique(self):
        """Test all interaction type values are unique."""
        values = [t.value for t in HitlInteractionType]
        assert len(values) == len(set(values)), "Duplicate interaction type values found"

    def test_interaction_type_enum_count(self):
        """Test expected number of interaction types."""
        # Document the expected count (update if new types added)
        expected_count = 8
        actual_count = len(list(HitlInteractionType))
        assert (
            actual_count == expected_count
        ), f"Expected {expected_count} types, got {actual_count}"
