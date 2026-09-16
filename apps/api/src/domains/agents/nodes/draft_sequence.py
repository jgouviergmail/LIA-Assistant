"""How the several drafts of one turn are decided (ADR-288).

A turn may prepare several drafts: two e-mails to two people, an e-mail and
an event, the N members of a FOR_EACH. The dispatch node presents ONE draft
per interrupt; these rules say what a decision on that draft does to the
others.

- A queue that is NOT a pre-approved lot is a SEQUENCE: a decision on the
  draft on screen is banked (``confirmed_drafts``) and the next draft is
  presented, with its own card, its own edit loop and its own edit counter.
  Nothing runs before the last answer.
- A pre-approved FOR_EACH lot (``pending_drafts_grouped``) is shown whole and
  confirmed whole: the person already approved the operation on the list.
- Settling never drops a draft in silence: what was queued after a terminal
  cancellation is reported cancelled, and the executor skips it.

Measured 2026-09-16 on Docker dev: two independent e-mails, one question on
the first, « Valider » sent both — the second never shown on a card, never
editable. The lot semantics had been applied to every multi-draft turn.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo

logger = structlog.get_logger(__name__)

# The draft-critique state keys (declared in ``MessagesState``).
STATE_KEY_PENDING_DRAFT_CRITIQUE = "pending_draft_critique"
STATE_KEY_PENDING_DRAFTS_QUEUE = "pending_drafts_queue"
STATE_KEY_PENDING_DRAFTS_GROUPED = "pending_drafts_grouped"
STATE_KEY_CONFIRMED_DRAFTS = "confirmed_drafts"
STATE_KEY_DRAFT_ACTION_RESULT = "draft_action_result"
# Replay-safe EDIT loop (2026-07): the loop state lives in the graph state,
# one interrupt per node execution.
STATE_KEY_DRAFT_EDIT_ITERATION = "draft_edit_iteration"
STATE_KEY_DRAFT_CLARIFICATION_QUESTION = "draft_clarification_question"

__all__ = [
    "draft_turn_reset",
    "STATE_KEY_CONFIRMED_DRAFTS",
    "STATE_KEY_DRAFT_ACTION_RESULT",
    "STATE_KEY_DRAFT_CLARIFICATION_QUESTION",
    "STATE_KEY_DRAFT_EDIT_ITERATION",
    "STATE_KEY_PENDING_DRAFTS_GROUPED",
    "STATE_KEY_PENDING_DRAFTS_QUEUE",
    "STATE_KEY_PENDING_DRAFT_CRITIQUE",
    "advance_sequence",
    "decision_entry",
    "settle",
]


def draft_turn_reset() -> dict[str, Any]:
    """What a NEW turn starts with, for the draft review: nothing pending.

    A new human message means the previous review was abandoned — the
    interrupt record expires after an hour, the checkpoint never does. A
    draft still pending there was re-presented by the next actionable turn,
    and the decisions banked along an abandoned sequence would have been
    executed by a later one. The router spreads this like the ReAct
    counters (``react_turn_reset``): one declaration, next to the keys.

    A HITL RESUME never runs the router (it re-enters the interrupted node),
    so a review in progress is untouched.

    Returns:
        Every draft-review key with its turn-start value.
    """
    return {
        STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
        STATE_KEY_PENDING_DRAFTS_QUEUE: [],
        STATE_KEY_PENDING_DRAFTS_GROUPED: False,
        STATE_KEY_CONFIRMED_DRAFTS: [],
        STATE_KEY_DRAFT_ACTION_RESULT: None,
        STATE_KEY_DRAFT_EDIT_ITERATION: 0,
        STATE_KEY_DRAFT_CLARIFICATION_QUESTION: None,
    }


def decision_entry(
    draft: PendingDraftInfo | dict[str, Any], action: str, reason: str | None = None
) -> dict[str, Any]:
    """One decided draft, in the shape the executor's batch reads."""
    if isinstance(draft, PendingDraftInfo):
        draft_id, draft_type, content = draft.draft_id, draft.draft_type, draft.draft_content
    else:
        draft_id = str(draft.get("draft_id", ""))
        draft_type = str(draft.get("draft_type", ""))
        content = draft.get("draft_content", {}) or {}
    entry: dict[str, Any] = {
        "action": action,
        "draft_id": draft_id,
        "draft_type": draft_type,
        "draft_content": content,
    }
    if reason:
        entry["reason"] = reason
    return entry


def advance_sequence(state: MessagesState, current: dict[str, Any]) -> dict[str, Any]:
    """Bank the decision on the draft on screen and present the next one.

    ADR-288: the next draft is a NEW ``pending_draft_critique``, so
    ``route_from_hitl_dispatch`` self-loops and the next interrupt runs in
    its own node execution, its edit loop starting from zero. No
    ``draft_action_result`` yet — nothing is executed before the last answer.
    """
    queue = list(state.get(STATE_KEY_PENDING_DRAFTS_QUEUE) or [])
    banked = [*(state.get(STATE_KEY_CONFIRMED_DRAFTS) or []), current]
    next_draft, remaining = queue[0], queue[1:]
    logger.info(
        "hitl_dispatch_sequence_advanced",
        decided_draft_id=current["draft_id"],
        decision=current["action"],
        next_draft_id=next_draft.get("draft_id"),
        position=len(banked) + 1,
        total=len(banked) + 1 + len(remaining),
    )
    return {
        STATE_KEY_PENDING_DRAFT_CRITIQUE: next_draft,
        STATE_KEY_PENDING_DRAFTS_QUEUE: remaining,
        STATE_KEY_CONFIRMED_DRAFTS: banked,
        STATE_KEY_DRAFT_EDIT_ITERATION: 0,
        STATE_KEY_DRAFT_CLARIFICATION_QUESTION: None,
    }


def settle(
    state: MessagesState, current: dict[str, Any], *, drop_reason: str | None = None
) -> dict[str, Any]:
    """The terminal state update: everything decided in this turn, at once.

    A pre-approved lot (``pending_drafts_grouped``) confirms its queue with the
    draft on screen; anything still queued otherwise is reported cancelled with
    ``drop_reason`` rather than dropped in silence. The result is the single
    decision when there is one, ``confirm_batch`` when several drafts were
    decided and at least one is to run, a plain cancellation when none is.
    """
    entries = [*(state.get(STATE_KEY_CONFIRMED_DRAFTS) or []), current]
    entries.extend(_queued_entries(state, current, drop_reason))
    return {
        STATE_KEY_PENDING_DRAFT_CRITIQUE: None,
        STATE_KEY_PENDING_DRAFTS_QUEUE: [],
        STATE_KEY_PENDING_DRAFTS_GROUPED: False,
        STATE_KEY_CONFIRMED_DRAFTS: [],
        STATE_KEY_DRAFT_ACTION_RESULT: _action_result(entries, current),
        STATE_KEY_DRAFT_EDIT_ITERATION: 0,
        STATE_KEY_DRAFT_CLARIFICATION_QUESTION: None,
    }


def _queued_entries(
    state: MessagesState, current: dict[str, Any], drop_reason: str | None
) -> list[dict[str, Any]]:
    """What becomes of the drafts still queued when the turn settles.

    A pre-approved lot confirmed by the draft on screen confirms them all;
    anything else reports them cancelled with the reason, never silently.
    """
    queue = list(state.get(STATE_KEY_PENDING_DRAFTS_QUEUE) or [])
    if not queue:
        return []
    grouped = bool(state.get(STATE_KEY_PENDING_DRAFTS_GROUPED))
    if grouped and current["action"] == DraftAction.CONFIRM.value:
        entries = [decision_entry(queued, DraftAction.CONFIRM.value) for queued in queue]
        logger.info(
            "hitl_dispatch_batch_draft_confirmed",
            primary_draft_id=current["draft_id"],
            batch_size=1 + len(entries),
            draft_ids=[current["draft_id"], *(entry["draft_id"] for entry in entries)],
        )
        return entries
    reason = drop_reason or current.get("reason") or "Cancelled with the draft on screen"
    return [decision_entry(queued, DraftAction.CANCEL.value, reason) for queued in queue]


def _action_result(entries: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    """The single decision, the ordered batch, or a plain cancellation."""
    if not any(entry["action"] == DraftAction.CONFIRM.value for entry in entries):
        return current
    if len(entries) == 1:
        return entries[0]
    return {"action": DraftAction.CONFIRM_BATCH.value, "batch": entries}
