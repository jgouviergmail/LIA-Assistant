"""
Unit tests for HITL Schemas.

Tests Pydantic schemas for HITL payloads and responses including:
- HitlSeverity enum
- HitlActionStyle enum
- HitlAction model
- HitlInterruptPayload model
- HitlUserResponse model
- Context models (DraftCritiqueContext, PlanApprovalContext, etc.)
- Standard action sets

@created: 2026-02-02
@coverage: schemas.py
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domains.agents.services.hitl.schemas import (
    STANDARD_DESTRUCTIVE_ACTIONS,
    STANDARD_DRAFT_ACTIONS,
    STANDARD_FOR_EACH_ACTIONS,
    STANDARD_PLAN_ACTIONS,
    ClarificationContext,
    DestructiveConfirmContext,
    DraftCritiqueContext,
    ForEachApprovalContext,
    HitlAction,
    HitlActionStyle,
    HitlInterruptPayload,
    HitlSeverity,
    HitlUserResponse,
    PlanApprovalContext,
)

# ============================================================================
# HitlSeverity Enum Tests
# ============================================================================


class TestHitlSeverityEnum:
    """Tests for HitlSeverity enumeration."""

    def test_severity_values(self):
        """Test all severity values exist."""
        assert HitlSeverity.INFO == "info"
        assert HitlSeverity.WARNING == "warning"
        assert HitlSeverity.CRITICAL == "critical"

    def test_severity_is_str_enum(self):
        """Test HitlSeverity inherits from str."""
        assert isinstance(HitlSeverity.INFO, str)
        assert HitlSeverity.INFO == "info"

    def test_severity_from_string(self):
        """Test creating severity from string value."""
        assert HitlSeverity("info") == HitlSeverity.INFO
        assert HitlSeverity("warning") == HitlSeverity.WARNING
        assert HitlSeverity("critical") == HitlSeverity.CRITICAL


# ============================================================================
# HitlActionStyle Enum Tests
# ============================================================================


class TestHitlActionStyleEnum:
    """Tests for HitlActionStyle enumeration."""

    def test_action_style_values(self):
        """Test all action style values exist."""
        assert HitlActionStyle.PRIMARY == "primary"
        assert HitlActionStyle.SECONDARY == "secondary"
        assert HitlActionStyle.DESTRUCTIVE == "destructive"
        assert HitlActionStyle.GHOST == "ghost"

    def test_action_style_is_str_enum(self):
        """Test HitlActionStyle inherits from str."""
        assert isinstance(HitlActionStyle.PRIMARY, str)


# ============================================================================
# HitlAction Model Tests
# ============================================================================


class TestHitlActionModel:
    """Tests for HitlAction Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating HitlAction with required fields only."""
        action = HitlAction(action="confirm", label="Confirm")
        assert action.action == "confirm"
        assert action.label == "Confirm"
        assert action.style == HitlActionStyle.SECONDARY  # default
        assert action.description is None
        assert action.keyboard_shortcut is None

    def test_create_with_all_fields(self):
        """Test creating HitlAction with all fields."""
        action = HitlAction(
            action="confirm",
            label="confirm_and_execute",
            style=HitlActionStyle.PRIMARY,
            description="Execute the plan",
            keyboard_shortcut="Enter",
        )
        assert action.action == "confirm"
        assert action.label == "confirm_and_execute"
        assert action.style == HitlActionStyle.PRIMARY
        assert action.description == "Execute the plan"
        assert action.keyboard_shortcut == "Enter"

    def test_missing_required_field_raises_error(self):
        """Test missing required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            HitlAction(action="confirm")  # Missing label

    def test_style_accepts_enum_value(self):
        """Test style accepts enum value."""
        action = HitlAction(
            action="test",
            label="Test",
            style=HitlActionStyle.DESTRUCTIVE,
        )
        assert action.style == HitlActionStyle.DESTRUCTIVE

    def test_style_accepts_string_value(self):
        """Test style accepts string value and converts to enum."""
        action = HitlAction(
            action="test",
            label="Test",
            style="primary",
        )
        assert action.style == HitlActionStyle.PRIMARY

    def test_model_serialization(self):
        """Test model can be serialized to dict."""
        action = HitlAction(
            action="confirm",
            label="Confirm",
            style=HitlActionStyle.PRIMARY,
        )
        data = action.model_dump()
        assert data["action"] == "confirm"
        assert data["label"] == "Confirm"
        assert data["style"] == "primary"


# ============================================================================
# HitlInterruptPayload Model Tests
# ============================================================================


class TestHitlInterruptPayloadModel:
    """Tests for HitlInterruptPayload Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating payload with required fields only."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
        )
        assert payload.message_id == "hitl_123"
        assert payload.conversation_id == "conv_456"
        assert payload.hitl_type == "plan_approval"

    def test_default_values(self):
        """Test default values are applied correctly."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
        )
        assert payload.available_actions == []
        assert payload.severity == HitlSeverity.INFO
        assert payload.context == {}
        assert payload.registry_ids == []
        assert payload.draft_type is None
        assert payload.draft_id is None
        assert payload.draft_content is None

    def test_created_at_auto_generated(self):
        """Test created_at is auto-generated with UTC timezone."""
        before = datetime.now(UTC)
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
        )
        after = datetime.now(UTC)
        assert before <= payload.created_at <= after
        assert payload.created_at.tzinfo is not None

    def test_with_actions_list(self):
        """Test payload with actions list."""
        actions = [
            HitlAction(action="approve", label="Approve"),
            HitlAction(action="reject", label="Reject"),
        ]
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
            available_actions=actions,
        )
        assert len(payload.available_actions) == 2
        assert payload.available_actions[0].action == "approve"

    def test_with_context_dict(self):
        """Test payload with context dict."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
            context={"plan_summary": {"steps": 3}, "reasons": ["test"]},
        )
        assert payload.context["plan_summary"]["steps"] == 3

    def test_with_registry_ids(self):
        """Test payload with registry_ids."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="draft_critique",
            registry_ids=["contact_abc123", "email_def456"],
        )
        assert len(payload.registry_ids) == 2
        assert "contact_abc123" in payload.registry_ids

    def test_draft_specific_fields(self):
        """Test draft-specific fields for draft_critique type."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="draft_critique",
            draft_type="email",
            draft_id="draft_789",
            draft_content={"to": "user@example.com", "subject": "Test"},
        )
        assert payload.draft_type == "email"
        assert payload.draft_id == "draft_789"
        assert payload.draft_content["to"] == "user@example.com"

    def test_severity_critical(self):
        """Test payload with CRITICAL severity."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="destructive_confirm",
            severity=HitlSeverity.CRITICAL,
        )
        assert payload.severity == HitlSeverity.CRITICAL

    def test_model_serialization(self):
        """Test payload can be serialized to dict."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
            severity=HitlSeverity.WARNING,
        )
        data = payload.model_dump()
        assert data["message_id"] == "hitl_123"
        assert data["severity"] == "warning"


# ============================================================================
# HitlUserResponse Model Tests
# ============================================================================


class TestHitlUserResponseModel:
    """Tests for HitlUserResponse Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating response with required fields only."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="confirm",
        )
        assert response.message_id == "hitl_123"
        assert response.action == "confirm"
        assert response.modifications is None
        assert response.feedback is None

    def test_create_with_all_fields(self):
        """Test creating response with all fields."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="edit",
            modifications={"query": "new query", "limit": 20},
            feedback="Changed the limit",
        )
        assert response.modifications == {"query": "new query", "limit": 20}
        assert response.feedback == "Changed the limit"

    def test_approve_action(self):
        """Test approve action response."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="approve",
        )
        assert response.action == "approve"

    def test_reject_action_with_feedback(self):
        """Test reject action with feedback."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="reject",
            feedback="I don't want to send this email",
        )
        assert response.action == "reject"
        assert response.feedback == "I don't want to send this email"

    def test_edit_action_with_modifications(self):
        """Test edit action with modifications."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="edit",
            modifications={"subject": "New Subject", "body": "Updated body"},
        )
        assert response.action == "edit"
        assert response.modifications["subject"] == "New Subject"

    def test_model_serialization(self):
        """Test response can be serialized to dict."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="confirm",
        )
        data = response.model_dump()
        assert data["message_id"] == "hitl_123"
        assert data["action"] == "confirm"


# ============================================================================
# DraftCritiqueContext Model Tests
# ============================================================================


class TestDraftCritiqueContextModel:
    """Tests for DraftCritiqueContext Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating context with required fields only."""
        context = DraftCritiqueContext(
            draft_type="email",
            draft_id="draft_123",
        )
        assert context.draft_type == "email"
        assert context.draft_id == "draft_123"
        assert context.draft_content == {}
        assert context.draft_summary is None

    def test_create_with_all_fields(self):
        """Test creating context with all fields."""
        context = DraftCritiqueContext(
            draft_type="event",
            draft_id="event_456",
            draft_content={"title": "Meeting", "date": "2026-02-03"},
            draft_summary="Meeting scheduled for tomorrow",
        )
        assert context.draft_type == "event"
        assert context.draft_content["title"] == "Meeting"
        assert context.draft_summary == "Meeting scheduled for tomorrow"

    def test_email_draft_type(self):
        """Test email draft type."""
        context = DraftCritiqueContext(
            draft_type="email",
            draft_id="email_789",
            draft_content={"to": "user@example.com", "subject": "Hello"},
        )
        assert context.draft_type == "email"


# ============================================================================
# ClarificationContext Model Tests
# ============================================================================


class TestClarificationContextModel:
    """Tests for ClarificationContext Pydantic model."""

    def test_create_with_defaults(self):
        """Test creating context with default values."""
        context = ClarificationContext()
        assert context.clarification_questions == []
        assert context.semantic_issues == []
        assert context.registry_ids == []

    def test_create_with_questions(self):
        """Test creating context with clarification questions."""
        context = ClarificationContext(
            clarification_questions=[
                "Which John do you mean?",
                "What time zone?",
            ]
        )
        assert len(context.clarification_questions) == 2
        assert "John" in context.clarification_questions[0]

    def test_create_with_semantic_issues(self):
        """Test creating context with semantic issues."""
        context = ClarificationContext(
            semantic_issues=[
                {
                    "type": "ambiguous_entity",
                    "entity": "John",
                    "options": ["John Smith", "John Doe"],
                },
            ]
        )
        assert len(context.semantic_issues) == 1
        assert context.semantic_issues[0]["type"] == "ambiguous_entity"

    def test_create_with_registry_ids(self):
        """Test creating context with registry IDs for rich rendering."""
        context = ClarificationContext(
            registry_ids=["contact_abc", "contact_def"],
        )
        assert len(context.registry_ids) == 2


# ============================================================================
# PlanApprovalContext Model Tests
# ============================================================================


class TestPlanApprovalContextModel:
    """Tests for PlanApprovalContext Pydantic model."""

    def test_create_with_defaults(self):
        """Test creating context with default values."""
        context = PlanApprovalContext()
        assert context.plan_summary == {}
        assert context.planned_actions == []
        assert context.approval_reasons == []

    def test_create_with_plan_summary(self):
        """Test creating context with plan summary."""
        context = PlanApprovalContext(
            plan_summary={
                "total_steps": 3,
                "domains": ["contacts", "emails"],
                "has_mutations": True,
            }
        )
        assert context.plan_summary["total_steps"] == 3
        assert "emails" in context.plan_summary["domains"]

    def test_create_with_planned_actions(self):
        """Test creating context with planned actions."""
        context = PlanApprovalContext(
            planned_actions=[
                {"step": 1, "tool": "search_contacts", "args": {"query": "John"}},
                {"step": 2, "tool": "send_email", "args": {"to": "john@example.com"}},
            ]
        )
        assert len(context.planned_actions) == 2
        assert context.planned_actions[1]["tool"] == "send_email"

    def test_create_with_approval_reasons(self):
        """Test creating context with approval reasons."""
        context = PlanApprovalContext(
            approval_reasons=[
                "Plan includes email sending",
                "Multiple recipients affected",
            ]
        )
        assert len(context.approval_reasons) == 2


# ============================================================================
# DestructiveConfirmContext Model Tests
# ============================================================================


class TestDestructiveConfirmContextModel:
    """Tests for DestructiveConfirmContext Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating context with required fields only."""
        context = DestructiveConfirmContext(operation_type="delete_emails")
        assert context.operation_type == "delete_emails"
        assert context.affected_count == 1
        assert context.affected_items == []
        assert "cannot be undone" in context.warning_message
        assert context.require_confirmation_text is False
        assert context.confirmation_text is None

    def test_create_with_all_fields(self):
        """Test creating context with all fields."""
        context = DestructiveConfirmContext(
            operation_type="delete_contacts",
            affected_count=50,
            affected_items=[
                {"name": "John Doe", "email": "john@example.com"},
                {"name": "Jane Smith", "email": "jane@example.com"},
            ],
            warning_message="This will permanently delete all selected contacts.",
            require_confirmation_text=True,
            confirmation_text="DELETE",
        )
        assert context.affected_count == 50
        assert len(context.affected_items) == 2
        assert context.require_confirmation_text is True
        assert context.confirmation_text == "DELETE"

    def test_bulk_delete_scenario(self):
        """Test bulk delete scenario configuration."""
        context = DestructiveConfirmContext(
            operation_type="delete_files",
            affected_count=100,
            warning_message="This will delete 100 files from your Drive.",
            require_confirmation_text=True,
            confirmation_text="DELETE ALL",
        )
        assert context.affected_count == 100
        assert context.confirmation_text == "DELETE ALL"


# ============================================================================
# ForEachApprovalContext Model Tests
# ============================================================================


class TestForEachApprovalContextModel:
    """Tests for ForEachApprovalContext Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating context with required fields only."""
        context = ForEachApprovalContext(
            iteration_count=15,
            collection_key="contacts",
            action_description="Send email to each contact",
            original_step_id="step_send_emails",
            tool_name="send_email_tool",
        )
        assert context.iteration_count == 15
        assert context.collection_key == "contacts"
        assert context.action_description == "Send email to each contact"
        assert context.original_step_id == "step_send_emails"
        assert context.tool_name == "send_email_tool"

    def test_default_values(self):
        """Test default values for optional fields."""
        context = ForEachApprovalContext(
            iteration_count=5,
            collection_key="events",
            action_description="Create reminder for each event",
            original_step_id="step_reminders",
            tool_name="create_reminder_tool",
        )
        assert context.preview_items == []
        assert context.for_each_max == 10
        assert context.estimated_duration_seconds is None

    def test_create_with_all_fields(self):
        """Test creating context with all fields."""
        context = ForEachApprovalContext(
            iteration_count=8,
            collection_key="contacts",
            action_description="Send birthday greeting to each contact",
            preview_items=[
                {"name": "John", "birthday": "2026-02-05"},
                {"name": "Jane", "birthday": "2026-02-06"},
                {"name": "Bob", "birthday": "2026-02-07"},
            ],
            for_each_max=5,
            estimated_duration_seconds=24.5,
            original_step_id="step_greetings",
            tool_name="send_greeting_tool",
        )
        assert len(context.preview_items) == 3
        assert context.for_each_max == 5
        assert context.estimated_duration_seconds == 24.5

    def test_preview_items_limited_to_max_five(self):
        """Test preview_items intended for max 5 items (UI constraint)."""
        # Model doesn't enforce this, but docs say max 5
        context = ForEachApprovalContext(
            iteration_count=10,
            collection_key="cities",
            action_description="Get weather for each city",
            preview_items=[{"city": f"City{i}"} for i in range(5)],
            original_step_id="step_weather",
            tool_name="get_weather_tool",
        )
        assert len(context.preview_items) == 5


# ============================================================================
# Standard Action Sets Tests
# ============================================================================


class TestStandardActionSets:
    """Tests for pre-defined standard action sets."""

    def test_standard_draft_actions(self):
        """Test STANDARD_DRAFT_ACTIONS has expected actions."""
        assert len(STANDARD_DRAFT_ACTIONS) == 3

        action_names = [a.action for a in STANDARD_DRAFT_ACTIONS]
        assert "confirm" in action_names
        assert "edit" in action_names
        assert "cancel" in action_names

        confirm_action = next(a for a in STANDARD_DRAFT_ACTIONS if a.action == "confirm")
        assert confirm_action.style == HitlActionStyle.PRIMARY
        assert confirm_action.keyboard_shortcut == "Enter"

    def test_standard_plan_actions(self):
        """Test STANDARD_PLAN_ACTIONS has expected actions."""
        assert len(STANDARD_PLAN_ACTIONS) == 2

        action_names = [a.action for a in STANDARD_PLAN_ACTIONS]
        assert "approve" in action_names
        assert "reject" in action_names

        approve_action = next(a for a in STANDARD_PLAN_ACTIONS if a.action == "approve")
        assert approve_action.style == HitlActionStyle.PRIMARY

        reject_action = next(a for a in STANDARD_PLAN_ACTIONS if a.action == "reject")
        assert reject_action.style == HitlActionStyle.DESTRUCTIVE

    def test_standard_destructive_actions(self):
        """Test STANDARD_DESTRUCTIVE_ACTIONS has expected actions."""
        assert len(STANDARD_DESTRUCTIVE_ACTIONS) == 2

        action_names = [a.action for a in STANDARD_DESTRUCTIVE_ACTIONS]
        assert "confirm_delete" in action_names
        assert "cancel" in action_names

        delete_action = next(
            a for a in STANDARD_DESTRUCTIVE_ACTIONS if a.action == "confirm_delete"
        )
        assert delete_action.style == HitlActionStyle.DESTRUCTIVE

    def test_standard_for_each_actions(self):
        """Test STANDARD_FOR_EACH_ACTIONS has expected actions."""
        assert len(STANDARD_FOR_EACH_ACTIONS) == 3

        action_names = [a.action for a in STANDARD_FOR_EACH_ACTIONS]
        assert "confirm_all" in action_names
        assert "limit" in action_names
        assert "cancel" in action_names

        confirm_all_action = next(a for a in STANDARD_FOR_EACH_ACTIONS if a.action == "confirm_all")
        assert confirm_all_action.style == HitlActionStyle.PRIMARY
        assert confirm_all_action.description is not None  # Has description

        limit_action = next(a for a in STANDARD_FOR_EACH_ACTIONS if a.action == "limit")
        assert limit_action.keyboard_shortcut == "L"

        cancel_action = next(a for a in STANDARD_FOR_EACH_ACTIONS if a.action == "cancel")
        assert cancel_action.style == HitlActionStyle.GHOST

    def test_all_standard_actions_have_labels(self):
        """Test all standard actions have labels (for i18n)."""
        all_actions = (
            STANDARD_DRAFT_ACTIONS
            + STANDARD_PLAN_ACTIONS
            + STANDARD_DESTRUCTIVE_ACTIONS
            + STANDARD_FOR_EACH_ACTIONS
        )

        for action in all_actions:
            assert action.label, f"Action {action.action} missing label"
            assert len(action.label) > 0


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestSchemaEdgeCases:
    """Edge cases and integration tests for schemas."""

    def test_payload_with_nested_context(self):
        """Test payload with deeply nested context."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
            context={"level1": {"level2": {"level3": {"value": "deep"}}}},
        )
        assert payload.context["level1"]["level2"]["level3"]["value"] == "deep"

    def test_payload_json_round_trip(self):
        """Test payload can be serialized and deserialized."""
        original = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="plan_approval",
            severity=HitlSeverity.WARNING,
            available_actions=[
                HitlAction(action="approve", label="Approve", style=HitlActionStyle.PRIMARY),
            ],
        )

        json_str = original.model_dump_json()
        restored = HitlInterruptPayload.model_validate_json(json_str)

        assert restored.message_id == original.message_id
        assert restored.severity == original.severity
        assert len(restored.available_actions) == 1
        assert restored.available_actions[0].action == "approve"

    def test_context_type_compatibility(self):
        """Test context types can be used with HitlInterruptPayload."""
        # Using typed context
        draft_context = DraftCritiqueContext(
            draft_type="email",
            draft_id="draft_123",
            draft_content={"to": "user@example.com"},
        )

        # Context as dict for payload
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="draft_critique",
            context=draft_context.model_dump(),
        )

        assert payload.context["draft_type"] == "email"
        assert payload.context["draft_id"] == "draft_123"

    def test_empty_actions_list_valid(self):
        """Test empty actions list is valid."""
        payload = HitlInterruptPayload(
            message_id="hitl_123",
            conversation_id="conv_456",
            hitl_type="info_only",
            available_actions=[],
        )
        assert payload.available_actions == []

    def test_user_response_with_empty_modifications(self):
        """Test user response with empty modifications dict."""
        response = HitlUserResponse(
            message_id="hitl_123",
            action="edit",
            modifications={},  # Empty but not None
        )
        assert response.modifications == {}
