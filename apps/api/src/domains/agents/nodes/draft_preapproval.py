"""A draft the person already approved on their ticket is not asked again (ADR-276, lot 7).

The HITL dispatch node presents every draft through ``interrupt()``. A
workboard run replaying an action the person approved ON THE TICKET carries
the identity of what they were shown — the draft type and the digest of its
content — and the rebuilt draft is let through on that exact identity and on
nothing looser: a different recipient, body or amount asks again with the new
preview (ADR-092, « what is confirmed is what was last displayed »). The
approval is SPENT on the match, so a second identical draft in the same run
asks too. Outside such a run the origin carries nothing, and the interrupt is
the plain one it always was.

Its own module rather than a branch in ``hitl_dispatch_node``: that node is
frozen by the size ratchet and ``_handle_draft_critique`` sits at CC 29, so the
rule lives here, as one call, and both ratchets hold.
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.types import interrupt

from src.domains.agents.api.run_origin import consume_approved_draft
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.effects.digest import drafts_digest
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo
from src.infrastructure.observability.metrics_workboard import workboard_replays_total

logger = structlog.get_logger(__name__)


def decide_draft(pending_draft: PendingDraftInfo, interrupt_payload: dict[str, Any]) -> Any:
    """Ask the person — unless they already approved THIS draft on their ticket.

    Args:
        pending_draft: The draft about to be presented.
        interrupt_payload: What the interrupt would carry.

    Returns:
        The decision — the person's, through the interrupt, or the approval
        they gave on the ticket, in the shape the dispatch node reads.
    """
    verdict = consume_approved_draft(
        pending_draft.draft_type, _identity(pending_draft, interrupt_payload)
    )
    if verdict is None:
        return interrupt(interrupt_payload)
    workboard_replays_total.labels(result="matched" if verdict else "mismatched").inc()
    logger.info(
        "hitl_dispatch_draft_replay",
        draft_id=pending_draft.draft_id,
        draft_type=pending_draft.draft_type,
        matched=verdict,
    )
    if verdict:
        return {"action": DraftAction.CONFIRM.value}
    return interrupt(interrupt_payload)


def _identity(pending_draft: PendingDraftInfo, interrupt_payload: dict[str, Any]) -> str:
    """What the person would be shown, as one identity.

    A batch presents its first draft and confirms them ALL on one answer, so
    the identity is the whole list the payload carries, in order — the SAME
    list the ticket run captured from the metadata chunk and stored.

    Args:
        pending_draft: The draft about to be presented.
        interrupt_payload: What the interrupt would carry.

    Returns:
        ``drafts_digest`` over the batch, or over the lone draft.
    """
    requests = interrupt_payload.get("action_requests") or []
    first = requests[0] if requests and isinstance(requests[0], dict) else {}
    batch = first.get("batch_drafts")
    if isinstance(batch, list) and len(batch) > 1:
        return drafts_digest([dict(item.get("draft_content") or {}) for item in batch])
    return drafts_digest([pending_draft.draft_content])


__all__ = ["decide_draft"]
