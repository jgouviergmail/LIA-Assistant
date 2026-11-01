"""The resume payload of a one-click HITL decision, per interrupt kind (Lot 1 option B).

A button carries certainty: the card the person clicked maps to its interrupt's
resume payload deterministically — no classifier, and by-construction parity
with the payloads the conversational branches produce for the same intents
(``approval_decision.py``). An unsupported (kind, action) pair maps to None,
which the caller turns into a stale-decision error: a click is an approval
gesture, never conversation content.

One builder per interrupt kind, in a table: adding a kind is an entry, never a
branch inside another kind's logic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from src.core.field_names import FIELD_DECISION, FIELD_DRAFT_ID
from src.domains.agents.constants import ACTION_TYPE_DRAFT_CRITIQUE
from src.domains.agents.context.choice_answer import (
    CHOICE_CANCEL,
    CHOICE_NONE,
    CHOICE_SELECT,
    ChoiceAnswer,
)
from src.domains.agents.services.hitl.protocols import HitlInteractionType

__all__ = ["structured_resume_payload"]

# Wire action ids emitted by the interactions are not uniform (e.g.
# destructive_confirm emits "confirm_delete", the for_each STANDARD set
# defines "confirm_all") — canonicalize them server-side so the frontend
# passes wire ids through verbatim and there is a single source of truth.
_STRUCTURED_ACTION_ALIASES: dict[str, str] = {
    "confirm": "confirm",
    "approve": "confirm",
    "confirm_delete": "confirm",
    "confirm_all": "confirm",
    # ADR-298: the egress card's second answer — a confirmation that narrows
    # the run. Canonised so every reader sees a confirmation; the narrowing
    # travels as its own field (_ACTION_FIELDS).
    "confirm_without_data": "confirm",
    "cancel": "cancel",
    "reject": "cancel",
    # The Telegram FOR_EACH keyboard's pair (hitl_keyboard._HITL_TYPE_BUTTONS):
    # a press is the chat card's own decision, never words to classify.
    "continue": "confirm",
    "stop": "cancel",
}

#: Wire actions that carry a decision FIELD beside the canonical action.
_ACTION_FIELDS: dict[str, dict[str, Any]] = {"confirm_without_data": {"share_turn_data": False}}

_DECLINED_BY_BUTTON: Final = "User declined via approval button"


def _confirmation(action: str, fields: dict[str, Any], *_: Any) -> dict[str, Any] | None:
    """A tool confirmation: confirm or cancel, with the fields the wire action adds."""
    return {"action": action, **fields} if action in ("confirm", "cancel") else None


def _draft_critique(
    action: str, fields: dict[str, Any], draft_id: str | None, instructions: str | None, *_: Any
) -> dict[str, Any] | None:
    """A draft card: confirm, cancel, or edit with the instructions typed beside it.

    The edit routes the LIVE draft_modifier loop, the payload the classifier's
    EDIT branch produces — instructions required. Per-field edit
    (updated_content) has no live execution path and stays rejected.
    """
    if action == "edit":
        text = (instructions or "").strip()
        if not text:
            return None
        return {"action": "edit", FIELD_DRAFT_ID: draft_id, "modification_instructions": text}
    payload = _confirmation(action, fields)
    if payload is not None:
        payload[FIELD_DRAFT_ID] = draft_id
        if action == "cancel":
            payload["reason"] = _DECLINED_BY_BUTTON
    return payload


def _clarification(action: str, *_: Any) -> dict[str, Any] | None:
    """Buttons on an open question only make sense for cancelling it."""
    return {"clarification": "", "cancelled": True} if action == "cancel" else None


def _choice(
    action: str, _fields: Any, _draft: Any, _text: Any, index: int | None
) -> dict[str, Any] | None:
    """Which shown item (ADR-367): an option's button carries its position."""
    if action == CHOICE_SELECT:
        return ChoiceAnswer(CHOICE_SELECT, index).resume() if index else None
    return ChoiceAnswer(action).resume() if action in (CHOICE_NONE, CHOICE_CANCEL) else None


def _decision(action: str, *_: Any) -> dict[str, Any] | None:
    """destructive_confirm / for_each_confirmation / plan approval / generic."""
    if action == "confirm":
        return {FIELD_DECISION: "APPROVE"}
    if action == "cancel":
        return {FIELD_DECISION: "REJECT", "rejection_reason": _DECLINED_BY_BUTTON}
    return None


_BUILDERS: dict[str, Callable[..., dict[str, Any] | None]] = {
    ACTION_TYPE_DRAFT_CRITIQUE: _draft_critique,
    "tool_confirmation": _confirmation,
    "clarification": _clarification,
    HitlInteractionType.ENTITY_DISAMBIGUATION.value: _choice,
}


def structured_resume_payload(
    interrupt_type: str,
    action: str,
    draft_id: str | None,
    modification_instructions: str | None = None,
    selected_index: int | None = None,
) -> dict[str, Any] | None:
    """The resume payload of a supported (interrupt kind, action) pair.

    Args:
        interrupt_type: The pending interrupt's kind.
        action: The wire action the card sent (aliases canonicalised here).
        draft_id: The draft a draft card is about.
        modification_instructions: The edit typed beside a draft card.
        selected_index: The option a « which one? » card's button names.

    Returns:
        The payload, or None for a pair no card can send.
    """
    fields = _ACTION_FIELDS.get(action, {})
    action = _STRUCTURED_ACTION_ALIASES.get(action, action)
    builder = _BUILDERS.get(interrupt_type, _decision)
    payload: dict[str, Any] | None = builder(
        action, fields, draft_id, modification_instructions, selected_index
    )
    return payload
