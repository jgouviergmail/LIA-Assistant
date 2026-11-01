"""The drafts one decision executed, read from its record.

Read by the business metrics (a verdict per executed draft) and by the response
after a plan resumed (every round's acts judged together, spec 2026-10-29 D7).
It lives with the drafts because both readers import this package already, and
neither may import the other: the metrics import the nodes package.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domains.agents.drafts.models import DraftAction


def executed_entries(draft_result: Mapping[str, Any]) -> list[Any]:
    """The drafts a decision executed: a batch's entries, the confirmed draft, or none.

    A cancellation executed nothing, nor did an edit (it asks again).

    Args:
        draft_result: A decision's execution record (``to_agent_result()``).

    Returns:
        The executed entries, in their order.
    """
    action = draft_result.get("action")
    if action == DraftAction.CONFIRM_BATCH.value:
        data = draft_result.get("data")
        return list(data.get("batch_results") or []) if isinstance(data, Mapping) else []
    return [draft_result] if action == DraftAction.CONFIRM.value else []
