"""HITL resume-decision parsing for :class:`OrchestrationService` (audit F015).

Classifies a user's natural-language reply to a Human-in-the-Loop interrupt into
the exact resume payload each interrupt kind expects. Extracted from the
``service.py`` monolith so the former CC-59 dispatcher becomes a small entrypoint
(:func:`parse_approval_decision`) delegating to focused per-branch helpers.

Contract per ``interrupt_type`` (unchanged from the original):
    - ``draft_critique`` / ``tool_confirmation`` -> ``{"action": ...}``
    - ``for_each_confirmation`` / plan approval / generic -> ``{"decision": ...}``
    - ``clarification`` -> ``{"clarification": <message>}`` (info passthrough)
      or ``{"clarification": <message>, "cancelled": True}`` (cancel intent)
    - stale/missing context -> ``{"decision": NEW_REQUEST, ...}``

Redis (interrupt context) and the LLM classifier are imported lazily inside the
functions that use them, so tests patch them at their source modules and no
import cycle is introduced.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_DECISION,
    FIELD_DRAFT_ID,
    FIELD_INTERRUPT_DATA,
    FIELD_TYPE,
)
from src.core.i18n import DEFAULT_LANGUAGE
from src.core.i18n_hitl import HitlMessages, HitlResumeMessage
from src.domains.agents.constants import (
    ACTION_TYPE_DRAFT_CRITIQUE,
    HITL_DECISION_NEW_REQUEST,
    INTENTION_UNKNOWN,
)

if TYPE_CHECKING:
    from src.domains.agents.services.hitl_classifier import ClassificationResult

logger = get_logger(__name__)

# Fast-path natural-language approval/rejection words (FR/EN) for HITL resume
# classification. Non-FR/EN responses fall through to the LLM classifier, which
# is i18n-aware. Single source of truth reused by every branch — draft critique
# adds the send verbs.
_HITL_CONFIRM_WORDS: frozenset[str] = frozenset(
    {"ok", "oui", "yes", "approve", "confirme", "confirmer", "d'accord", "dacord"}
)
_HITL_CANCEL_WORDS: frozenset[str] = frozenset(
    {"non", "no", "reject", "refuse", "annule", "annuler", "cancel"}
)
# Draft critique additionally fast-paths the send verbs (email drafts).
_HITL_CONFIRM_WORDS_DRAFT: frozenset[str] = _HITL_CONFIRM_WORDS | frozenset({"envoie", "envoyer"})


async def _fetch_interrupt_context(
    conversation_id: uuid.UUID, run_id: str
) -> tuple[list[dict[str, Any]], str | None, str | None, dict[str, Any] | None]:
    """Fetch pending HITL context from Redis.

    Args:
        conversation_id: Conversation UUID for the Redis lookup.
        run_id: Run ID for logging.

    Returns:
        ``(action_context, interrupt_type, draft_id, pending_data)``. On any Redis
        error the context is empty, which the caller treats as a stale/new request.
    """
    from src.core.config import settings
    from src.domains.agents.utils import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    action_context: list[dict[str, Any]] = []
    interrupt_type: str | None = None
    draft_id: str | None = None
    pending_data: dict[str, Any] | None = None

    try:
        redis = await get_redis_cache()
        hitl_store = HITLStore(
            redis_client=redis,
            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
        )
        pending_data = await hitl_store.get_interrupt(str(conversation_id))
        if pending_data and FIELD_INTERRUPT_DATA in pending_data:
            action_context = pending_data[FIELD_INTERRUPT_DATA].get(FIELD_ACTION_REQUESTS, [])
            # Detect interrupt type from first action request
            if action_context:
                first_action = action_context[0]
                interrupt_type = first_action.get(FIELD_TYPE, INTENTION_UNKNOWN)
                # For draft_critique, extract draft_id
                if interrupt_type == ACTION_TYPE_DRAFT_CRITIQUE:
                    draft_id = first_action.get(FIELD_DRAFT_ID, INTENTION_UNKNOWN)
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as redis_err:
        logger.warning(
            "approval_decision_redis_fetch_failed",
            run_id=run_id,
            error=str(redis_err),
            error_type=type(redis_err).__name__,
            fallback="proceeding without interrupt context",
        )

    return action_context, interrupt_type, draft_id, pending_data


def _map_draft_critique_result(
    result: ClassificationResult,
    draft_id: str | None,
    user_message: str,
    run_id: str,
    user_language: str,
) -> dict[str, Any]:
    """Map a classifier result to a ``draft_critique`` resume payload.

    Args:
        result: Classifier output for the user's reply.
        draft_id: Draft the reply is about.
        user_message: Raw reply, reused as edit instructions when the classifier
            extracted none.
        run_id: Run ID for logging.
        user_language: Language the fallback question is emitted in — it is
            streamed verbatim to the user (see :class:`HitlResumeMessage`).

    Returns:
        The ``{"action": ...}`` resume payload.
    """
    if result.decision == "APPROVE":
        return {"action": "confirm", "draft_id": draft_id}

    if result.decision == "REJECT":
        return {"action": "cancel", "draft_id": draft_id, "reason": result.reasoning}

    if result.decision == "EDIT":
        modification_instructions = ""
        if result.edited_params:
            modification_instructions = result.edited_params.get("modification_instructions", "")
        if not modification_instructions:
            modification_instructions = user_message
        logger.info(
            "approval_decision_draft_critique_edit",
            run_id=run_id,
            draft_id=draft_id,
            modification_instructions=modification_instructions[:100],
        )
        return {
            "action": "edit",
            "draft_id": draft_id,
            "modification_instructions": modification_instructions,
        }

    if result.decision == "AMBIGUOUS":
        logger.info(
            "approval_decision_draft_critique_ambiguous",
            run_id=run_id,
            draft_id=draft_id,
            clarification=result.clarification_question,
        )
        return {
            "action": "clarify",
            "draft_id": draft_id,
            "clarification_question": result.clarification_question
            or HitlMessages.get_resume_message(
                HitlResumeMessage.CLARIFY_WHAT_TO_CHANGE, user_language
            ),
        }

    if result.decision == "REPLAN":
        # For draft_critique, REPLAN means "modify the draft content", not an
        # action change — convert to EDIT (the classifier sometimes misreads
        # "modifie..." as an action change).
        logger.info(
            "approval_decision_draft_critique_replan_as_edit",
            run_id=run_id,
            draft_id=draft_id,
            original_decision="REPLAN",
            converted_to="EDIT",
        )
        modification_instructions = ""
        if result.edited_params:
            modification_instructions = result.edited_params.get(
                "reformulated_intent", ""
            ) or result.edited_params.get("modification_instructions", "")
        if not modification_instructions:
            modification_instructions = user_message
        return {
            "action": "edit",
            "draft_id": draft_id,
            "modification_instructions": modification_instructions,
        }

    logger.warning(
        "approval_decision_draft_critique_unknown",
        run_id=run_id,
        decision=result.decision,
    )
    return {
        "action": "cancel",
        # Technical diagnostic, not user copy: `decision` is a Literal whose five
        # values are all handled above, so this branch is defensive only.
        "reason": f"unknown classification: {result.decision}",
        "draft_id": draft_id,
    }


async def _classify_draft_critique(
    user_message: str,
    message_lower: str,
    action_context: list[dict[str, Any]],
    draft_id: str | None,
    run_id: str,
    user_language: str,
) -> dict[str, Any]:
    """Classify a ``draft_critique`` reply into a ``{"action": ...}`` payload."""
    logger.info(
        "approval_decision_draft_critique_detected",
        run_id=run_id,
        user_message=user_message[:50],
        draft_id=draft_id,
    )

    if message_lower in _HITL_CONFIRM_WORDS_DRAFT:
        logger.info("approval_decision_draft_critique_confirm", run_id=run_id, draft_id=draft_id)
        return {"action": "confirm", "draft_id": draft_id}

    if message_lower in _HITL_CANCEL_WORDS:
        logger.info("approval_decision_draft_critique_cancel", run_id=run_id, draft_id=draft_id)
        return {"action": "cancel", "draft_id": draft_id}

    # Complex response — use the LLM classifier to detect EDIT intent.
    try:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        logger.info(
            "approval_decision_draft_critique_using_classifier",
            run_id=run_id,
            user_message=user_message[:100],
            draft_id=draft_id,
        )
        classifier = HitlResponseClassifier()
        result = await classifier.classify(
            user_response=user_message, action_context=action_context
        )
        logger.info(
            "approval_decision_draft_critique_classified",
            run_id=run_id,
            decision=result.decision,
            confidence=result.confidence,
            has_edited_params=bool(result.edited_params),
        )
        return _map_draft_critique_result(result, draft_id, user_message, run_id, user_language)
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        # Classifier failed — a complex response after seeing a draft means the
        # user wants to MODIFY it; fall back to EDIT with their message.
        logger.warning(
            "approval_decision_draft_critique_classifier_error_fallback_to_edit",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            fallback="edit",
            user_message=user_message[:100],
        )
        return {
            "action": "edit",
            "draft_id": draft_id,
            "modification_instructions": user_message,
        }


def _map_for_each_result(
    result: ClassificationResult, user_message: str, run_id: str, user_language: str
) -> dict[str, Any]:
    """Map a classifier result to a ``for_each_confirmation`` resume payload.

    Args:
        result: Classifier output for the user's reply.
        user_message: Raw reply, reused as exclusion criteria when the classifier
            extracted none.
        run_id: Run ID for logging.
        user_language: Language the ambiguity notice is emitted in.

    Returns:
        The ``{"decision": ...}`` resume payload.
    """
    if result.decision == "APPROVE":
        return {"decision": "APPROVE"}

    if result.decision == "REJECT":
        return {
            "decision": "REJECT",
            "rejection_reason": result.reasoning or "User cancelled",
        }

    if result.decision == "EDIT":
        exclude_criteria = ""
        if result.edited_params:
            exclude_criteria = result.edited_params.get("exclude_criteria", "")
        if not exclude_criteria:
            exclude_criteria = user_message
        logger.info(
            "approval_decision_for_each_edit",
            run_id=run_id,
            exclude_criteria=exclude_criteria[:100],
        )
        return {"decision": "EDIT", "exclude_criteria": exclude_criteria}

    if result.decision == "REPLAN":
        # REPLAN = user wants a different set — treat as EDIT excluding via message.
        logger.info(
            "approval_decision_for_each_replan_as_edit",
            run_id=run_id,
            original_decision="REPLAN",
            converted_to="EDIT",
        )
        return {"decision": "EDIT", "exclude_criteria": user_message}

    if result.decision == "AMBIGUOUS":
        return {
            "decision": "REJECT",
            "rejection_reason": result.clarification_question
            or HitlMessages.get_resume_message(
                HitlResumeMessage.AMBIGUOUS_CANCELLED, user_language
            ),
        }

    logger.warning("approval_decision_for_each_unknown", run_id=run_id, decision=result.decision)
    return {
        "decision": "REJECT",
        # Technical diagnostic (defensive branch): every Literal value is handled above.
        "rejection_reason": f"unknown classification: {result.decision}",
    }


async def _classify_for_each(
    user_message: str, action_context: list[dict[str, Any]], run_id: str, user_language: str
) -> dict[str, Any]:
    """Classify a ``for_each_confirmation`` reply (always via the LLM classifier)."""
    logger.info(
        "approval_decision_for_each_confirmation_detected",
        run_id=run_id,
        user_message=user_message[:50],
    )

    try:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        classifier = HitlResponseClassifier()
        result = await classifier.classify(
            user_response=user_message, action_context=action_context
        )
        logger.info(
            "approval_decision_for_each_classified",
            run_id=run_id,
            decision=result.decision,
            confidence=result.confidence,
            has_edited_params=bool(result.edited_params),
        )
        return _map_for_each_result(result, user_message, run_id, user_language)
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        # Classifier failed — treat the message as EDIT exclusion criteria.
        logger.warning(
            "approval_decision_for_each_classifier_error_fallback_to_edit",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            fallback="edit",
            user_message=user_message[:100],
        )
        return {"decision": "EDIT", "exclude_criteria": user_message}


async def _classify_tool_confirmation(
    user_message: str,
    message_lower: str,
    action_context: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Classify a ``tool_confirmation`` reply into ``{"action": ...}``.

    This gates a mutation, so any non-approval (reject / ambiguous / classifier
    failure) maps to ``cancel`` — never execute a mutation without an explicit
    confirmation.
    """
    if message_lower in _HITL_CONFIRM_WORDS:
        return {"action": "confirm"}
    if message_lower in _HITL_CANCEL_WORDS:
        return {"action": "cancel"}
    try:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        classifier = HitlResponseClassifier()
        result = await classifier.classify(
            user_response=user_message, action_context=action_context
        )
        logger.info(
            "approval_decision_tool_confirmation_classified",
            run_id=run_id,
            decision=result.decision,
            confidence=result.confidence,
        )
        if result.decision == "APPROVE":
            return {"action": "confirm"}
        return {"action": "cancel", "reason": result.reasoning or "declined"}
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        logger.warning(
            "approval_decision_tool_confirmation_classifier_error",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            fallback="cancel",
        )
        return {"action": "cancel", "reason": "classification_failed"}


def _map_generic_result(
    result: ClassificationResult,
    action_context: list[dict[str, Any]],
    run_id: str,
    user_language: str,
) -> dict[str, Any]:
    """Map a classifier result to a generic (plan-level) ``{"decision": ...}`` payload.

    Args:
        result: Classifier output for the user's reply.
        action_context: Pending action requests, used to build plan modifications.
        run_id: Run ID for logging.
        user_language: Language the ambiguity notice is emitted in — it reaches
            the response node as the rejection summary.

    Returns:
        The ``{"decision": ...}`` resume payload.
    """
    if result.decision == "APPROVE":
        return {"decision": "APPROVE"}

    if result.decision == "REJECT":
        return {
            "decision": "REJECT",
            "rejection_reason": result.reasoning or "User declined",
        }

    if result.decision == "EDIT":
        # Format expected by approval_gate_node:
        # [{"modification_type": "edit_params", "step_id": "step_X", "new_parameters": {...}}]
        modifications: list[dict[str, Any]] = []
        if result.edited_params and action_context:
            from src.domains.agents.services.hitl.resumption_strategies import (
                _build_plan_modifications_from_classifier,
            )

            modifications = _build_plan_modifications_from_classifier(
                edited_params=result.edited_params,
                pending_action_requests=action_context,
                run_id=run_id,
            )
        return {
            "decision": "EDIT",
            "modifications": modifications,
            "edited_params": result.edited_params,
        }

    if result.decision == "REPLAN":
        replan_instructions = ""
        if result.edited_params:
            replan_instructions = result.edited_params.get(
                "reformulated_intent", ""
            ) or result.edited_params.get("new_action", "")
        logger.info(
            "approval_decision_replan",
            run_id=run_id,
            has_instructions=bool(replan_instructions),
            reasoning=result.reasoning[:100] if result.reasoning else None,
        )
        return {
            "decision": "REPLAN",
            "replan_instructions": replan_instructions,
            "edited_params": result.edited_params,
        }

    if result.decision == "AMBIGUOUS":
        logger.warning(
            "approval_decision_ambiguous",
            run_id=run_id,
            clarification=result.clarification_question,
        )
        return {
            "decision": "REJECT",
            "rejection_reason": result.clarification_question
            or HitlMessages.get_resume_message(HitlResumeMessage.AMBIGUOUS_SPECIFY, user_language),
        }

    logger.warning("approval_decision_unknown_type", run_id=run_id, decision=result.decision)
    return {
        "decision": "REJECT",
        # Technical diagnostic (defensive branch): every Literal value is handled above.
        "rejection_reason": f"unknown classification: {result.decision}",
    }


async def _classify_clarification(
    user_message: str,
    message_lower: str,
    action_context: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Map a clarification reply: raw-text passthrough, except a clear cancel.

    Lot 1 Phase 0 (runtime-proven defect): without an abort path, a cancel
    intent loops — the bare word fast-pathed to a plan-level ``{"decision":
    "REJECT"}`` the clarification_node ignores, and a full cancel phrase
    passed through as clarification text the planner dutifully replanned
    with. Both re-triggered the same interrupt.

    Abort rules (conservative — a wrongly aborted flow loses the user's
    info, a wrongly passed-through cancel just loops once more):
        - exact cancel word -> abort, no LLM call;
        - otherwise the classifier decides: REJECT at/above the configured
          confidence threshold with no edited params -> abort;
        - anything else (info reply, low confidence, classifier error)
          -> passthrough of the raw text.
    """
    from src.core.config import settings

    if message_lower in _HITL_CANCEL_WORDS:
        logger.info(
            "approval_decision_clarification_cancel_fast_path",
            run_id=run_id,
            user_message=user_message[:50],
        )
        return {"clarification": user_message, "cancelled": True}

    try:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        classifier = HitlResponseClassifier()
        result = await classifier.classify(
            user_response=user_message, action_context=action_context
        )
        if (
            result is not None
            and result.decision == "REJECT"
            and result.confidence >= settings.hitl_classifier_confidence_threshold
            and not result.edited_params
        ):
            logger.info(
                "approval_decision_clarification_cancel_classified",
                run_id=run_id,
                confidence=result.confidence,
                user_message=user_message[:50],
            )
            return {"clarification": user_message, "cancelled": True}
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        logger.warning(
            "approval_decision_clarification_classifier_error",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            fallback="passthrough",
        )

    logger.info(
        "approval_decision_clarification_passthrough",
        run_id=run_id,
        user_message=user_message[:100],
    )
    return {"clarification": user_message}


async def _classify_generic(
    user_message: str,
    message_lower: str,
    action_context: list[dict[str, Any]],
    interrupt_type: str | None,
    run_id: str,
    user_language: str,
) -> dict[str, Any]:
    """Classify a generic / plan-level reply into a ``{"decision": ...}`` payload.

    Handles the confirm/reject fast paths and the LLM-classified slow path
    (with a safe REJECT fallback on classifier error). Clarification replies
    are dispatched to :func:`_classify_clarification` upstream.
    """
    if message_lower in _HITL_CONFIRM_WORDS:
        logger.info(
            "approval_decision_fast_path",
            run_id=run_id,
            decision="APPROVE",
            user_message=user_message[:50],
        )
        return {"decision": "APPROVE"}

    if message_lower in _HITL_CANCEL_WORDS:
        logger.info(
            "approval_decision_fast_path",
            run_id=run_id,
            decision="REJECT",
            user_message=user_message[:50],
        )
        return {"decision": "REJECT", "rejection_reason": "User declined"}

    try:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        logger.info(
            "approval_decision_using_classifier",
            run_id=run_id,
            user_message=user_message[:100],
            action_context_count=len(action_context),
            interrupt_type=interrupt_type,
        )

        classifier = HitlResponseClassifier()
        result = await classifier.classify(
            user_response=user_message, action_context=action_context
        )
        logger.info(
            "approval_decision_classified",
            run_id=run_id,
            decision=result.decision,
            confidence=result.confidence,
            reasoning=result.reasoning[:100] if result.reasoning else None,
            has_edited_params=bool(result.edited_params),
        )
        return _map_generic_result(result, action_context, run_id, user_language)
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
        logger.error(
            "approval_decision_classifier_error",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            user_message=user_message[:100],
        )
        # English scaffolding, like the sibling "User declined": this reason is
        # summarized by the response node, which writes to the user in their own
        # language. The exception type alone — never its message, which can carry
        # raw payload fragments into the prompt.
        return {
            "decision": "REJECT",
            "rejection_reason": f"classification failed ({type(e).__name__})",
        }


class HitlDecisionStaleError(Exception):
    """A structured hitl_decision cannot be applied to the pending interrupt.

    Raised when the pending interrupt is missing, its message_id does not
    match the decision's, or the (interrupt_type, action) pair is not
    supported. The caller MUST emit a typed error chunk
    (``error_code="hitl_decision_stale"``) and stop — the message is never
    processed as a new turn (fail-closed: a button click is an approval
    gesture, not conversation content).
    """


# Wire action ids emitted by the interactions are not uniform (e.g.
# destructive_confirm emits "confirm_delete", the for_each STANDARD set
# defines "confirm_all") — canonicalize them server-side so the frontend
# passes wire ids through verbatim and there is a single source of truth.
_STRUCTURED_ACTION_ALIASES: dict[str, str] = {
    "confirm": "confirm",
    "approve": "confirm",
    "confirm_delete": "confirm",
    "confirm_all": "confirm",
    "cancel": "cancel",
    "reject": "cancel",
}


# (interrupt_type, action) -> resume payload builders for one-click approvals.
# Scope: confirm/cancel (V1) + draft edit with modification instructions
# (P1-V2 — routes the LIVE draft_modifier loop, same payload the classifier
# EDIT branch produces). Per-field edit (updated_content) has NO live
# execution path (dead code on the whole chain) and stays rejected.
def _structured_resume_payload(
    interrupt_type: str,
    action: str,
    draft_id: str | None,
    modification_instructions: str | None = None,
) -> dict[str, Any] | None:
    """Return the resume payload for a supported (type, action) pair, else None."""
    action = _STRUCTURED_ACTION_ALIASES.get(action, action)
    if interrupt_type == ACTION_TYPE_DRAFT_CRITIQUE and action == "edit":
        # Parity with _map_draft_critique_result EDIT: instructions required.
        instructions = (modification_instructions or "").strip()
        if not instructions:
            return None
        return {
            "action": "edit",
            FIELD_DRAFT_ID: draft_id,
            "modification_instructions": instructions,
        }
    if interrupt_type in ("tool_confirmation", "draft_critique"):
        if action not in ("confirm", "cancel"):
            return None
        payload: dict[str, Any] = {"action": action}
        if interrupt_type == ACTION_TYPE_DRAFT_CRITIQUE:
            payload[FIELD_DRAFT_ID] = draft_id
            if action == "cancel":
                payload["reason"] = "User declined via approval button"
        return payload
    if interrupt_type == "clarification":
        # Buttons on an open question only make sense for cancelling it.
        if action != "cancel":
            return None
        return {"clarification": "", "cancelled": True}
    # destructive_confirm / for_each_confirmation / plan approval / generic
    if action == "confirm":
        return {FIELD_DECISION: "APPROVE"}
    if action == "cancel":
        return {FIELD_DECISION: "REJECT", "rejection_reason": "User declined via approval button"}
    return None


async def build_structured_decision(
    hitl_decision: dict[str, Any], conversation_id: uuid.UUID, run_id: str
) -> dict[str, Any]:
    """Map a structured one-click decision to the interrupt's resume payload.

    Deterministic counterpart of :func:`parse_approval_decision` for approval
    buttons (Lot 1 option B): no LLM classifier call, and by-construction
    parity — the payload shapes are exactly the ones the conversational
    branches produce for the same intents.

    Args:
        hitl_decision: ``{"message_id": ..., "action": "confirm"|"cancel"}``
            as sent by the frontend card.
        conversation_id: Conversation UUID for the Redis pending lookup.
        run_id: Run ID for logging.

    Returns:
        The interrupt-kind-specific resume payload.

    Raises:
        HitlDecisionStaleError: No pending interrupt, message_id mismatch,
            or unsupported (interrupt_type, action) pair — fail-closed.
    """
    action_context, interrupt_type, draft_id, pending_data = await _fetch_interrupt_context(
        conversation_id, run_id
    )

    if not action_context or interrupt_type is None:
        raise HitlDecisionStaleError("no pending interrupt for structured decision")

    # Freshness check: the card the user clicked must be the pending one.
    # Legacy pendings stored before message_id persistence are tolerated
    # (bounded by the pending TTL after deployment).
    stored_message_id = (pending_data or {}).get(FIELD_INTERRUPT_DATA, {}).get("message_id")
    decision_message_id = hitl_decision.get("message_id")
    if stored_message_id and decision_message_id and stored_message_id != decision_message_id:
        raise HitlDecisionStaleError(
            f"message_id mismatch: pending={stored_message_id} decision={decision_message_id}"
        )

    action = str(hitl_decision.get("action", "")).lower()
    raw_instructions = hitl_decision.get("modification_instructions")
    payload = _structured_resume_payload(
        interrupt_type,
        action,
        draft_id,
        modification_instructions=(raw_instructions if isinstance(raw_instructions, str) else None),
    )
    if payload is None:
        raise HitlDecisionStaleError(
            f"unsupported structured action {action!r} for interrupt_type {interrupt_type!r}"
        )

    logger.info(
        "structured_hitl_decision_built",
        run_id=run_id,
        interrupt_type=interrupt_type,
        action=action,
        classifier_bypassed=True,
    )
    return payload


async def parse_approval_decision(
    user_message: str,
    conversation_id: uuid.UUID,
    run_id: str,
    user_language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Parse a user's natural-language HITL reply into a resume payload.

    Fetches the pending interrupt context, then dispatches on ``interrupt_type``
    to the matching classifier. A missing/stale context returns a NEW_REQUEST
    signal so the caller treats the message as a fresh turn rather than a resume.

    Args:
        user_message: User's response message.
        conversation_id: Conversation UUID for Redis lookup.
        run_id: Run ID for logging.
        user_language: Language of the static notices this may emit (ambiguity,
            clarification). Some are streamed verbatim to the user, so the caller
            passes the language from the checkpointed state; the configured
            default only applies when it has none.

    Returns:
        The interrupt-kind-specific resume payload (see module docstring).
    """
    message_lower = user_message.lower().strip()

    action_context, interrupt_type, draft_id, pending_data = await _fetch_interrupt_context(
        conversation_id, run_id
    )

    # Stale/invalid HITL resumption: pending data without action_context is not a
    # real resume — signal the caller to treat it as a new request.
    if not action_context:
        logger.warning(
            "approval_decision_no_action_context",
            run_id=run_id,
            user_message=user_message[:50],
            interrupt_type=interrupt_type,
            has_pending_data=pending_data is not None,
            reason="No action_context found - treating as new request, not HITL resumption",
        )
        return {
            FIELD_DECISION: HITL_DECISION_NEW_REQUEST,
            "user_message": user_message,
            "reason": "Missing action_context - stale HITL state",
        }

    if interrupt_type == "draft_critique":
        return await _classify_draft_critique(
            user_message, message_lower, action_context, draft_id, run_id, user_language
        )
    if interrupt_type == "for_each_confirmation":
        return await _classify_for_each(user_message, action_context, run_id, user_language)
    if interrupt_type == "tool_confirmation":
        return await _classify_tool_confirmation(
            user_message, message_lower, action_context, run_id
        )
    if interrupt_type == "clarification":
        return await _classify_clarification(user_message, message_lower, action_context, run_id)
    return await _classify_generic(
        user_message, message_lower, action_context, interrupt_type, run_id, user_language
    )
