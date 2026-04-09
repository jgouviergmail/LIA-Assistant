"""
Unit tests for ReactToolWrapper.

Phase: ADR-070 — ReAct Execution Mode
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper


def _make_mock_tool(name: str = "test_tool") -> MagicMock:
    """Create a mock BaseTool with standard attributes."""
    mock = MagicMock()
    mock.name = name
    mock.description = f"Test tool: {name}"
    mock.args_schema = None
    mock.ainvoke = AsyncMock()
    return mock


@pytest.mark.unit
class TestReactToolWrapper:
    """Tests for ReactToolWrapper."""

    def test_preserves_tool_interface(self) -> None:
        """Wrapper preserves original tool's name and description."""
        original = _make_mock_tool("search_contacts")
        wrapper = ReactToolWrapper(original_tool=original, hitl_required=False)
        assert wrapper.name == "search_contacts"
        assert wrapper.description == "Test tool: search_contacts"
        assert wrapper.hitl_required is False

    def test_hitl_required_flag(self) -> None:
        """Wrapper correctly stores hitl_required flag."""
        original = _make_mock_tool("send_email")
        wrapper = ReactToolWrapper(original_tool=original, hitl_required=True)
        assert wrapper.hitl_required is True

    @pytest.mark.asyncio
    async def test_returns_string_from_dict_result(self) -> None:
        """Dict result → returns message field as string."""
        original = _make_mock_tool()
        original.ainvoke = AsyncMock(return_value={"message": "Found 3 contacts", "success": True})
        wrapper = ReactToolWrapper(original_tool=original)
        result = await wrapper._arun()
        assert result == "Found 3 contacts"

    @pytest.mark.asyncio
    async def test_returns_string_from_string_result(self) -> None:
        """String result → passthrough."""
        original = _make_mock_tool()
        original.ainvoke = AsyncMock(return_value="Direct string result")
        wrapper = ReactToolWrapper(original_tool=original)
        result = await wrapper._arun()
        assert result == "Direct string result"

    @pytest.mark.asyncio
    async def test_collects_registry_from_dict(self) -> None:
        """Registry updates in dict result are accumulated."""
        original = _make_mock_tool()
        original.ainvoke = AsyncMock(
            return_value={
                "message": "Found contact",
                "registry_updates": {"contact_abc": {"type": "CONTACT", "data": {}}},
            }
        )
        wrapper = ReactToolWrapper(original_tool=original)
        await wrapper._arun()
        assert "contact_abc" in wrapper._accumulated_registry

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self) -> None:
        """Exception → returns error string (no crash)."""
        original = _make_mock_tool()
        original.ainvoke = AsyncMock(side_effect=RuntimeError("API timeout"))
        wrapper = ReactToolWrapper(original_tool=original)
        result = await wrapper._arun()
        assert "ERROR:" in result
        assert "API timeout" in result

    @pytest.mark.asyncio
    async def test_collects_registry_from_unified_output(self) -> None:
        """UnifiedToolOutput-like object → registry collected, message returned."""
        # Simulate a UnifiedToolOutput (has .message and .registry_updates)
        mock_output = MagicMock()
        mock_output.message = "3 events found"
        mock_output.registry_updates = {"event_123": {"type": "EVENT"}}
        mock_output.tool_metadata = {}
        mock_output.structured_data = {}  # Empty → no data appended

        original = _make_mock_tool()
        original.ainvoke = AsyncMock(return_value=mock_output)
        wrapper = ReactToolWrapper(original_tool=original)
        result = await wrapper._arun()
        assert result == "3 events found"
        assert "event_123" in wrapper._accumulated_registry

    @pytest.mark.asyncio
    async def test_collects_draft_metadata(self) -> None:
        """Tool returning requires_confirmation → draft collected."""
        mock_output = MagicMock()
        mock_output.message = "Email draft created"
        mock_output.registry_updates = {"draft_abc": {"type": "DRAFT"}}
        mock_output.structured_data = {}  # Empty → no data appended
        mock_output.tool_metadata = {
            "requires_confirmation": True,
            "draft_id": "draft_abc",
            "draft_type": "email",
            "draft_content": {"to": "marc@test.com", "subject": "Hello"},
        }
        mock_output.summary_for_llm = "Email to marc@test.com"

        original = _make_mock_tool("send_email_tool")
        original.ainvoke = AsyncMock(return_value=mock_output)
        wrapper = ReactToolWrapper(original_tool=original)
        result = await wrapper._arun()
        assert result == "Email draft created"
        assert len(wrapper._accumulated_drafts) == 1
        assert wrapper._accumulated_drafts[0]["draft_id"] == "draft_abc"
        assert wrapper._accumulated_drafts[0]["tool_name"] == "send_email_tool"
