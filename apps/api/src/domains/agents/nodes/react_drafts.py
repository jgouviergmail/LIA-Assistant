"""Reading a draft off a ReAct tool result.

Extracted from ``react_nodes`` (file-size ratchet, ADR-298): the one reader
of « did this tool prepare a DRAFT rather than act? », shared by the node
that hands drafts to the dispatch and by the egress question that settles
one in place (``react_egress_question``) — which must not import the node.
"""

from __future__ import annotations

from typing import Any


def extract_draft_info(raw_result: Any, tool_name: str) -> dict[str, Any] | None:
    """Extract draft metadata from a tool result requiring confirmation.

    Mirrors the pipeline's ``parallel_executor`` draft detection so the ReAct
    loop can hand a prepared draft off to the shared draft_critique HITL flow.
    A mutation tool (create/update/delete) returns ``requires_confirmation=True``
    and stores the executable payload in its registry item — the actual action
    is only performed after the user confirms.

    Args:
        raw_result: Raw tool output (``UnifiedToolOutput`` for draft tools).
        tool_name: Name of the tool that produced the result.

    Returns:
        A ``PendingDraftInfo``-compatible dict (draft_id, draft_type,
        draft_content, draft_summary, registry_ids, tool_name, step_id), or
        ``None`` when the result is not a confirmable draft.
    """
    tool_metadata = getattr(raw_result, "tool_metadata", None)
    if not isinstance(tool_metadata, dict) or not tool_metadata.get("requires_confirmation"):
        return None

    draft_id = tool_metadata.get("draft_id")
    if not draft_id:
        return None

    registry_updates = getattr(raw_result, "registry_updates", None) or {}

    # Extract the executable draft content from the registry item payload — the
    # same source the pipeline's DraftExecutor consumes to perform the real action.
    draft_content: dict[str, Any] = {}
    item = registry_updates.get(draft_id)
    if item is not None:
        payload = getattr(item, "payload", None)
        if payload is None and isinstance(item, dict):
            payload = item.get("payload")
        if isinstance(payload, dict):
            draft_content = payload.get("content") or {}

    return {
        "draft_id": draft_id,
        "draft_type": tool_metadata.get("draft_type"),
        "draft_content": draft_content,
        "draft_summary": getattr(raw_result, "summary_for_llm", "") or "",
        "registry_ids": list(registry_updates.keys()),
        "tool_name": tool_name,
        "step_id": None,
    }


__all__ = ["extract_draft_info"]
