"""Reading the drafts off a ReAct tool result.

Extracted from ``react_nodes`` (file-size ratchet, ADR-298): the reader of
« did this tool prepare DRAFTS rather than act? », shared by the node that
hands drafts to the dispatch and by the egress question that settles one in
place (``react_egress_question``) — which must not import the node.

It reads through the pipeline's own reader (``step_results.drafts_of``), so
both modes see the same drafts in one call — and an iterative MCP task can
hand up several (spec 2026-10-29 D5).
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.orchestration.step_results import drafts_of


def extract_drafts(raw_result: Any, tool_name: str) -> list[dict[str, Any]]:
    """Every draft a tool result asks the person to confirm, in its order.

    A mutation tool (create/update/delete) returns ``requires_confirmation=True``
    and stores the executable payload in its registry item — the action is only
    performed after the user confirms. The ReAct loop presents the first and
    queues the rest (``react_call_execution._draft_update``).

    Args:
        raw_result: Raw tool output (``UnifiedToolOutput`` for draft tools).
        tool_name: Name of the tool that produced the result.

    Returns:
        ``PendingDraftInfo``-compatible dicts (draft_id, draft_type,
        draft_content, draft_summary, registry_ids, tool_name, step_id); empty
        when the result is not a confirmable draft.
    """
    return drafts_of(raw_result, tool_name, None)


__all__ = ["extract_drafts"]
