"""One action contract for live and restored draft approval cards."""

from collections.abc import Sequence
from typing import Any

from src.domains.agents.drafts.models import DraftAction, DraftType

from .schemas import SANDBOX_EGRESS_ACTIONS, SANDBOX_EGRESS_ACTIONS_NO_DATA


def draft_available_actions(draft_type: str, draft_content: dict[str, Any]) -> list[dict[str, Any]]:
    """Publish the scopes the draft accepts, including the no-data-only variant."""
    if draft_type == DraftType.SANDBOX_EGRESS.value:
        summary = draft_content.get("data_summary")
        available = not isinstance(summary, dict) or summary.get("available", True)
        actions = SANDBOX_EGRESS_ACTIONS if available else SANDBOX_EGRESS_ACTIONS_NO_DATA
        return [{"action": a.action, "label": a.label, "style": a.style.value} for a in actions]
    return [
        {"action": DraftAction.CONFIRM.value, "label": "confirm", "style": "primary"},
        {"action": DraftAction.EDIT.value, "label": "edit", "style": "secondary"},
        {"action": DraftAction.CANCEL.value, "label": "cancel", "style": "destructive"},
    ]


def with_available_actions(
    requests: list[dict[str, Any]],
    published: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Retain replay fields, copy published buttons and repair legacy drafts.

    The stream's presentation contains fewer replay fields than the interrupt.
    Only its actions are projected back; neither input is mutated. Old records
    predate action persistence and use the same draft contract at read time.
    """
    result = []
    for index, request in enumerate(requests):
        presentation = published[index] if index < len(published) else request
        actions = presentation.get("available_actions") or request.get("available_actions")
        if not actions and request.get("type") == "draft_critique":
            actions = draft_available_actions(
                request.get("draft_type", "unknown"), request.get("draft_content") or {}
            )
        result.append({**request, "available_actions": actions} if actions else request)
    return result
