"""Unit tests for ReAct draft detection (_extract_draft_info).

These cover the draft HITL handoff logic added so that mutation tools
(create/update/delete) trigger the shared draft_critique confirmation flow in
ReAct mode instead of being silently dropped (the agent otherwise hallucinated
"done" without ever executing the action).

Phase: ADR-070 — ReAct Execution Mode (draft HITL parity)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.agents.nodes.react_nodes import _extract_draft_info


def _make_draft_output(
    *,
    requires_confirmation: bool = True,
    draft_id: str | None = "draft_xyz",
    draft_type: str | None = "event",
    payload_content: dict[str, Any] | None = None,
    summary: str = "Event 'Test' on 2026-05-21",
    registry_item_as_dict: bool = False,
) -> MagicMock:
    """Build a UnifiedToolOutput-like mock for a draft-producing tool.

    Mirrors the real shape: ``tool_metadata`` carries requires_confirmation +
    ids, and the executable content lives in the registry item payload under
    the ``content`` key (see DraftService._draft_to_registry_item).
    """
    output = MagicMock()
    output.tool_metadata = {
        "requires_confirmation": requires_confirmation,
        "draft_id": draft_id,
        "draft_type": draft_type,
    }
    output.summary_for_llm = summary

    if draft_id is not None:
        payload = {"content": payload_content} if payload_content is not None else {}
        if registry_item_as_dict:
            item: Any = {"payload": payload}
        else:
            item = MagicMock()
            item.payload = payload
        output.registry_updates = {draft_id: item}
    else:
        output.registry_updates = {}
    return output


@pytest.mark.unit
class TestExtractDraftInfo:
    """Tests for _extract_draft_info."""

    def test_detects_draft_and_extracts_content_from_object_payload(self) -> None:
        """requires_confirmation + registry item object → full PendingDraftInfo dict."""
        content = {"summary": "Test", "start_datetime": "2026-05-21T15:00:00"}
        output = _make_draft_output(payload_content=content)

        info = _extract_draft_info(output, "create_event_tool")

        assert info is not None
        assert info["draft_id"] == "draft_xyz"
        assert info["draft_type"] == "event"
        assert info["draft_content"] == content
        assert info["draft_summary"] == "Event 'Test' on 2026-05-21"
        assert info["registry_ids"] == ["draft_xyz"]
        assert info["tool_name"] == "create_event_tool"
        assert info["step_id"] is None

    def test_extracts_content_from_dict_payload(self) -> None:
        """Registry item serialized as a dict → content still extracted."""
        content = {"to": "marc@test.com", "subject": "Hello"}
        output = _make_draft_output(
            draft_type="email", payload_content=content, registry_item_as_dict=True
        )

        info = _extract_draft_info(output, "send_email_tool")

        assert info is not None
        assert info["draft_content"] == content
        assert info["draft_type"] == "email"

    def test_not_a_draft_when_requires_confirmation_false(self) -> None:
        """A non-draft tool result (no confirmation) → None."""
        output = _make_draft_output(requires_confirmation=False)
        assert _extract_draft_info(output, "get_events_tool") is None

    def test_not_a_draft_when_no_tool_metadata(self) -> None:
        """A plain dict result (no tool_metadata attribute) → None."""
        assert _extract_draft_info({"message": "ok"}, "some_tool") is None

    def test_not_a_draft_when_missing_draft_id(self) -> None:
        """requires_confirmation but no draft_id → None (defensive)."""
        output = _make_draft_output(draft_id=None)
        assert _extract_draft_info(output, "create_event_tool") is None

    def test_missing_content_yields_empty_dict(self) -> None:
        """Registry payload without a content key → empty draft_content, no crash."""
        output = _make_draft_output(payload_content=None)
        info = _extract_draft_info(output, "create_event_tool")
        assert info is not None
        assert info["draft_content"] == {}

    def test_draft_id_not_in_registry_yields_empty_content(self) -> None:
        """draft_id absent from registry_updates → empty content, still a draft."""
        output = _make_draft_output(payload_content={"summary": "X"})
        output.registry_updates = {}  # draft_id no longer present
        info = _extract_draft_info(output, "create_event_tool")
        assert info is not None
        assert info["draft_content"] == {}
        assert info["registry_ids"] == []
