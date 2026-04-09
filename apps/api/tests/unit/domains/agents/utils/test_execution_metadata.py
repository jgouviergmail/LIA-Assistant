"""
Unit tests for execution metadata utilities.

Tests for extracting display metadata for SSE events
during execution steps.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.field_names import FIELD_STATUS
from src.domains.agents.utils.execution_metadata import (
    DEFAULT_NODE_METADATA,
    DefaultDisplayMetadata,
    build_execution_step_event,
    get_node_display_metadata,
    get_tool_display_metadata,
    should_emit_execution_step,
)

# Path to patch get_global_registry (it's imported inside the function)
REGISTRY_PATCH_PATH = "src.domains.agents.registry.agent_registry.get_global_registry"


# ============================================================================
# Tests for DefaultDisplayMetadata dataclass
# ============================================================================


class TestDefaultDisplayMetadata:
    """Tests for DefaultDisplayMetadata dataclass."""

    def test_create_with_required_fields(self):
        """Test creating metadata with required fields only."""
        metadata = DefaultDisplayMetadata(
            emoji="🔍",
            i18n_key="search_action",
        )

        assert metadata.emoji == "🔍"
        assert metadata.i18n_key == "search_action"
        assert metadata.visible is True  # default
        assert metadata.category == "system"  # default

    def test_create_with_all_fields(self):
        """Test creating metadata with all fields."""
        metadata = DefaultDisplayMetadata(
            emoji="📧",
            i18n_key="send_email",
            visible=False,
            category="tool",
        )

        assert metadata.emoji == "📧"
        assert metadata.i18n_key == "send_email"
        assert metadata.visible is False
        assert metadata.category == "tool"

    def test_is_frozen(self):
        """Test that metadata is immutable (frozen)."""
        metadata = DefaultDisplayMetadata(
            emoji="🔍",
            i18n_key="test",
        )

        with pytest.raises(AttributeError):
            metadata.emoji = "❌"  # type: ignore

    def test_category_literal_types(self):
        """Test different category values."""
        for category in ["system", "agent", "tool", "context"]:
            metadata = DefaultDisplayMetadata(
                emoji="🔍",
                i18n_key="test",
                category=category,  # type: ignore
            )
            assert metadata.category == category


# ============================================================================
# Tests for DEFAULT_NODE_METADATA
# ============================================================================


class TestDefaultNodeMetadata:
    """Tests for default node metadata dictionary."""

    def test_contains_expected_nodes(self):
        """Test that all expected system nodes are defined."""
        expected_nodes = [
            "router",
            "planner",
            "semantic_validator",
            "clarification",
            "approval_gate",
            "task_orchestrator",
            "response",
        ]

        for node in expected_nodes:
            assert node in DEFAULT_NODE_METADATA

    def test_all_entries_have_required_fields(self):
        """Test all entries have required metadata fields."""
        for node_name, metadata in DEFAULT_NODE_METADATA.items():
            assert isinstance(metadata, DefaultDisplayMetadata)
            assert metadata.emoji, f"{node_name} missing emoji"
            assert metadata.i18n_key, f"{node_name} missing i18n_key"
            assert metadata.category in ["system", "agent", "tool", "context"]

    def test_all_system_nodes_are_visible(self):
        """Test that all system nodes default to visible."""
        for node_name, metadata in DEFAULT_NODE_METADATA.items():
            assert metadata.visible is True, f"{node_name} should be visible"

    def test_router_metadata(self):
        """Test router node metadata specifically."""
        router = DEFAULT_NODE_METADATA["router"]
        assert router.emoji == "🧭"
        assert router.i18n_key == "router_decision"
        assert router.category == "system"

    def test_planner_metadata(self):
        """Test planner node metadata specifically."""
        planner = DEFAULT_NODE_METADATA["planner"]
        assert planner.emoji == "📋"
        assert planner.i18n_key == "planner_generation"

    def test_response_metadata(self):
        """Test response node metadata specifically."""
        response = DEFAULT_NODE_METADATA["response"]
        assert response.emoji == "💬"
        assert response.i18n_key == "response_generation"


# ============================================================================
# Tests for get_tool_display_metadata
# ============================================================================


class TestGetToolDisplayMetadata:
    """Tests for tool display metadata retrieval."""

    def test_returns_metadata_when_found(self):
        """Test returning metadata when tool is found in registry."""
        # Mock the registry and tool manifest
        mock_display = MagicMock()
        mock_display.emoji = "🔍"
        mock_display.i18n_key = "get_contacts"
        mock_display.visible = True
        mock_display.category = "tool"

        mock_manifest = MagicMock()
        mock_manifest.display = mock_display

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = get_tool_display_metadata("get_contacts_tool")

        assert result == mock_display
        mock_registry.get_tool_manifest.assert_called_once_with("get_contacts_tool")

    def test_returns_none_when_tool_not_found(self):
        """Test returning None when tool is not in registry."""
        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = None

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = get_tool_display_metadata("unknown_tool")

        assert result is None

    def test_returns_none_when_no_display_metadata(self):
        """Test returning None when tool has no display metadata."""
        mock_manifest = MagicMock()
        mock_manifest.display = None

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = get_tool_display_metadata("tool_without_display")

        assert result is None

    def test_graceful_degradation_on_exception(self):
        """Test graceful degradation when exception occurs."""
        with patch(REGISTRY_PATCH_PATH, side_effect=Exception("Registry error")):
            with patch("src.domains.agents.utils.execution_metadata.logger") as mock_logger:
                result = get_tool_display_metadata("any_tool")

        assert result is None
        mock_logger.warning.assert_called()


# ============================================================================
# Tests for get_node_display_metadata
# ============================================================================


class TestGetNodeDisplayMetadata:
    """Tests for node display metadata retrieval."""

    def test_returns_metadata_for_known_nodes(self):
        """Test returning metadata for known system nodes."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            for node_name in ["router", "planner", "response"]:
                result = get_node_display_metadata(node_name)
                assert result is not None
                assert isinstance(result, DefaultDisplayMetadata)

    def test_returns_correct_metadata_for_router(self):
        """Test correct metadata returned for router node."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = get_node_display_metadata("router")

        assert result is not None
        assert result.emoji == "🧭"
        assert result.i18n_key == "router_decision"

    def test_returns_none_for_unknown_node(self):
        """Test returning None for unknown node."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = get_node_display_metadata("unknown_node")

        assert result is None

    def test_returns_none_for_agent_node(self):
        """Test returning None for agent nodes (not configured)."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = get_node_display_metadata("contacts_agent")

        # Agent nodes are not in DEFAULT_NODE_METADATA currently
        assert result is None

    @pytest.mark.parametrize("node_name", list(DEFAULT_NODE_METADATA.keys()))
    def test_all_default_nodes_return_metadata(self, node_name):
        """Test all nodes in DEFAULT_NODE_METADATA return proper metadata."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = get_node_display_metadata(node_name)

        assert result is not None
        assert result == DEFAULT_NODE_METADATA[node_name]


# ============================================================================
# Tests for should_emit_execution_step
# ============================================================================


class TestShouldEmitExecutionStep:
    """Tests for execution step emission decision."""

    def test_tool_with_visible_metadata_returns_true(self):
        """Test tool with visible metadata returns True."""
        mock_display = MagicMock()
        mock_display.visible = True

        mock_manifest = MagicMock()
        mock_manifest.display = mock_display

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = should_emit_execution_step("tool", "some_tool")

        assert result is True

    def test_tool_with_hidden_metadata_returns_false(self):
        """Test tool with visible=False returns False."""
        mock_display = MagicMock()
        mock_display.visible = False

        mock_manifest = MagicMock()
        mock_manifest.display = mock_display

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = should_emit_execution_step("tool", "hidden_tool")

        assert result is False

    def test_tool_without_metadata_returns_false(self):
        """Test tool without metadata returns False."""
        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = None

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = should_emit_execution_step("tool", "unknown_tool")

        assert result is False

    def test_node_with_visible_metadata_returns_true(self):
        """Test known node returns True."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = should_emit_execution_step("node", "router")

        assert result is True

    def test_node_without_metadata_returns_false(self):
        """Test unknown node returns False."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = should_emit_execution_step("node", "unknown_node")

        assert result is False

    def test_invalid_step_type_returns_false(self):
        """Test invalid step type returns False."""
        with patch("src.domains.agents.utils.execution_metadata.logger") as mock_logger:
            result = should_emit_execution_step("invalid", "test")  # type: ignore

        assert result is False
        mock_logger.warning.assert_called()


# ============================================================================
# Tests for build_execution_step_event
# ============================================================================


class TestBuildExecutionStepEvent:
    """Tests for execution step event building."""

    def test_returns_none_when_should_not_emit(self):
        """Test returns None when step should not be emitted."""
        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = None

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = build_execution_step_event("tool", "unknown_tool")

        assert result is None

    def test_builds_tool_event_correctly(self):
        """Test building tool event with correct structure."""
        mock_display = MagicMock()
        mock_display.emoji = "🔍"
        mock_display.i18n_key = "get_contacts"
        mock_display.visible = True
        mock_display.category = "tool"

        mock_manifest = MagicMock()
        mock_manifest.display = mock_display

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                result = build_execution_step_event(
                    step_type="tool",
                    step_name="get_contacts_tool",
                    status="started",
                )

        assert result is not None
        assert result["type"] == "execution_step"
        assert result["step_type"] == "tool"
        assert result["step_name"] == "get_contacts_tool"
        assert result[FIELD_STATUS] == "started"
        assert result["emoji"] == "🔍"
        assert result["i18n_key"] == "get_contacts"
        assert result["category"] == "tool"

    def test_builds_node_event_correctly(self):
        """Test building node event with correct structure."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = build_execution_step_event(
                step_type="node",
                step_name="router",
                status="completed",
            )

        assert result is not None
        assert result["type"] == "execution_step"
        assert result["step_type"] == "node"
        assert result["step_name"] == "router"
        assert result[FIELD_STATUS] == "completed"
        assert result["emoji"] == "🧭"
        assert result["i18n_key"] == "router_decision"

    def test_includes_additional_data(self):
        """Test that additional_data is merged into event."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = build_execution_step_event(
                step_type="node",
                step_name="planner",
                status="started",
                additional_data={"custom_field": "custom_value", "count": 5},
            )

        assert result is not None
        assert result["custom_field"] == "custom_value"
        assert result["count"] == 5

    def test_status_values(self):
        """Test different status values."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            for status in ["started", "completed", "failed"]:
                result = build_execution_step_event(
                    step_type="node",
                    step_name="response",
                    status=status,  # type: ignore
                )

                assert result is not None
                assert result[FIELD_STATUS] == status

    def test_default_status_is_started(self):
        """Test default status is 'started'."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            result = build_execution_step_event(
                step_type="node",
                step_name="router",
            )

        assert result is not None
        assert result[FIELD_STATUS] == "started"


# ============================================================================
# Integration tests
# ============================================================================


class TestExecutionMetadataIntegration:
    """Integration tests for execution metadata flow."""

    def test_complete_tool_flow(self):
        """Test complete flow for tool execution events."""
        mock_display = MagicMock()
        mock_display.emoji = "📧"
        mock_display.i18n_key = "send_email"
        mock_display.visible = True
        mock_display.category = "tool"

        mock_manifest = MagicMock()
        mock_manifest.display = mock_display

        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = mock_manifest

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                # Check if should emit
                should_emit = should_emit_execution_step("tool", "send_email_tool")
                assert should_emit is True

                # Get metadata
                metadata = get_tool_display_metadata("send_email_tool")
                assert metadata is not None

                # Build event
                event = build_execution_step_event("tool", "send_email_tool", "completed")
                assert event is not None
                assert event["emoji"] == "📧"

    def test_complete_node_flow(self):
        """Test complete flow for node execution events."""
        with patch("src.domains.agents.utils.execution_metadata.logger"):
            # Check if should emit
            should_emit = should_emit_execution_step("node", "semantic_validator")
            assert should_emit is True

            # Get metadata
            metadata = get_node_display_metadata("semantic_validator")
            assert metadata is not None
            assert metadata.emoji == "🔎"

            # Build event
            event = build_execution_step_event("node", "semantic_validator", "started")
            assert event is not None
            assert event["i18n_key"] == "semantic_validation"

    def test_sse_event_simulation(self):
        """Test simulating SSE event generation during execution."""
        events = []

        with patch("src.domains.agents.utils.execution_metadata.logger"):
            # Simulate execution flow
            nodes = ["router", "planner", "task_orchestrator", "response"]

            for node in nodes:
                # Started event
                started = build_execution_step_event("node", node, "started")
                if started:
                    events.append(started)

                # Completed event
                completed = build_execution_step_event("node", node, "completed")
                if completed:
                    events.append(completed)

        # Each node should produce 2 events (started + completed)
        assert len(events) == len(nodes) * 2

        # Check all events have correct structure
        for event in events:
            assert "type" in event
            assert "emoji" in event
            assert "i18n_key" in event

    def test_graceful_handling_of_unknown_steps(self):
        """Test that unknown steps are handled gracefully."""
        mock_registry = MagicMock()
        mock_registry.get_tool_manifest.return_value = None

        with patch(REGISTRY_PATCH_PATH, return_value=mock_registry):
            with patch("src.domains.agents.utils.execution_metadata.logger"):
                # Unknown tool
                tool_result = build_execution_step_event("tool", "fantasy_tool")
                assert tool_result is None

                # Unknown node
                node_result = build_execution_step_event("node", "fantasy_node")
                assert node_result is None

                # Should not raise any exceptions - just return None
