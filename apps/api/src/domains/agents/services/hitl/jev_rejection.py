"""Recognize only a total withdrawal; every other reply uses the original classifier."""

import json
from typing import TYPE_CHECKING, Any

from src.core.constants import JEV_HITL_REJECTION_MIN_CONFIDENCE
from src.core.context import current_tracker
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, ChoiceQuestion
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_jev import jev_decisions_total

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext


def _rejection_owner() -> TrackingContext | None:
    """Only an active tracker may own this optional native decision."""
    tracker = current_tracker.get()
    context = runtime_context_if_running()
    if (
        tracker is None
        or not tracker.run_id
        or (context is not None and context.user_id != tracker.user_id)
    ):
        return None
    return tracker


def _accepted_rejection(
    outcome: str,
    answer: ChoiceAnswer | None,
    pending_actions: list[dict[str, Any]],
    snapshot: list[dict[str, Any]],
) -> bool:
    """Accept the bounded verdict only while the judged actions are unchanged."""
    return (
        outcome == "success"
        and answer is not None
        and answer.choice == "reject_all"
        and answer.confidence >= JEV_HITL_REJECTION_MIN_CONFIDENCE
        and pending_actions == snapshot
    )


async def try_reject_all(
    user_reply: str, pending_actions: list[dict[str, Any]]
) -> ChoiceAnswer | None:
    """Keep the current account/run; a callback argument is never an account owner."""
    tracker = _rejection_owner()
    if tracker is None or not pending_actions or not user_reply.strip():
        return None
    try:
        snapshot = json.loads(json.dumps(pending_actions, ensure_ascii=False, allow_nan=False))
    except ValueError, TypeError, RecursionError:
        return None

    try:
        question = ChoiceQuestion.model_validate_json(
            load_prompt("jev_hitl_rejection_question", version="v1")
        )
        attempt = await choose_with_jev(
            usage=JevUsage.HITL_REJECTION,
            user_id=tracker.user_id,
            run_id=tracker.run_id,
            state={"user_reply": user_reply, "pending_actions": snapshot},
            question=question,
        )
    except Exception as exc:  # noqa: BLE001 — optional inference must preserve the classifier
        logger.warning("jev_hitl_rejection_unavailable", error_type=type(exc).__name__)
        return None

    answer = attempt.answer
    selected = _accepted_rejection(attempt.outcome, answer, pending_actions, snapshot)
    outcome = (
        "selected"
        if selected
        else ("uncertain" if attempt.outcome == "success" else attempt.outcome)
    )
    await record_action(
        tracker.user_id,
        attempt.diagnostic,
        action="selected" if selected else "fallback",
        outcome=outcome,
        target="hitl_rejected" if selected else "hitl_classifier",
        decision_labels={"selection": "Total rejection of the proposed actions"},
    )
    jev_decisions_total.labels(usage=JevUsage.HITL_REJECTION, outcome=outcome).inc()
    return answer if selected else None
