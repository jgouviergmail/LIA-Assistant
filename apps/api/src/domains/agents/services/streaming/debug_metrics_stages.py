"""Debug-panel stage sections (v2): the stages the panel could not see.

Sibling of ``DebugMetricsBuilder`` (kept separate for the file-size ratchet):
each function adds ONE optional section to the ``debug_metrics`` dict in
place, independently guarded so a failure in one never loses the others —
the same isolation doctrine as the builder.

State values may arrive as live objects (in-process stream) or as dicts
reconstructed from a checkpoint (HITL resume), so every read goes through
``_field`` which accepts both shapes.
"""

from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# The compaction summary is conversation-derived content: preview only.
_SUMMARY_PREVIEW_CHARS = 400


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a dataclass/model attribute or a dict key."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _enum_value(value: Any) -> Any:
    """Unwrap an Enum to its value; pass anything else through."""
    return getattr(value, "value", value)


def build_execution_mode(debug_metrics: dict[str, Any], state: dict[str, Any] | None) -> None:
    """Surface which engine ran the turn (``pipeline`` is the default mode).

    Args:
        debug_metrics: Debug payload mutated in place.
        state: Final graph state (may be None on degraded paths).
    """
    mode = (state or {}).get("execution_mode") or "pipeline"
    debug_metrics["execution_mode"] = mode


def build_semantic_validation(debug_metrics: dict[str, Any], state: dict[str, Any] | None) -> None:
    """Serialize the semantic-validator verdict for the panel.

    ADR-184 doctrine: a validation verdict is informative, never a blocker —
    the section exists precisely so a rejected-but-executed plan can be
    understood instead of imagined.

    Args:
        debug_metrics: Debug payload mutated in place.
        state: Final graph state carrying ``semantic_validation``.
    """
    result = (state or {}).get("semantic_validation")
    if result is None:
        return
    try:
        issues = []
        for issue in _field(result, "issues", []) or []:
            issues.append(
                {
                    "issue_type": _enum_value(_field(issue, "issue_type")),
                    "description": _field(issue, "description"),
                    "severity": _field(issue, "severity", "medium"),
                    "step_index": _field(issue, "step_index"),
                    "suggested_fix": _field(issue, "suggested_fix"),
                }
            )
        debug_metrics["semantic_validation"] = {
            "is_valid": bool(_field(result, "is_valid", True)),
            "confidence": float(_field(result, "confidence", 0.0) or 0.0),
            "criticality": _enum_value(_field(result, "criticality")),
            "requires_clarification": bool(_field(result, "requires_clarification", False)),
            "clarification_questions": list(_field(result, "clarification_questions", []) or []),
            "validation_duration_seconds": float(
                _field(result, "validation_duration_seconds", 0.0) or 0.0
            ),
            "used_fallback": bool(_field(result, "used_fallback", False)),
            "fallback_reason": _field(result, "fallback_reason"),
            "issues": issues,
        }
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("debug_metrics_semantic_validation_failed", error=str(err))


def build_react_execution(debug_metrics: dict[str, Any], state: dict[str, Any] | None) -> None:
    """Surface the ReAct loop (iterations, bound, tools) when it ran.

    The enforced iteration bound travels with the value it constrains
    (ADR-184: an enforced-but-hidden bound is a trap, not a contract).

    Args:
        debug_metrics: Debug payload mutated in place.
        state: Final graph state carrying the ``react_*`` keys.
    """
    state = state or {}
    iterations = int(state.get("react_iteration") or 0)
    if state.get("execution_mode") != "react" and iterations == 0:
        return
    try:
        from src.core.config import get_settings

        debug_metrics["react_execution"] = {
            "iterations": iterations,
            "max_iterations": get_settings().react_agent_max_iterations,
            "elapsed_seconds": float(state.get("react_elapsed_seconds") or 0.0),
            "tool_names": list(state.get("react_tool_names") or []),
            "executed_tool_calls": len(state.get("react_call_digests") or {}),
            # ADR-249 — the code the model wrote, admin surface only (owner
            # arbitration): it never reaches the answer.
            "scripts": list(state.get("react_scripts") or []),
        }
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("debug_metrics_react_execution_failed", error=str(err))


def build_hitl(
    debug_metrics: dict[str, Any],
    state: dict[str, Any] | None,
    hitl_interrupt: dict[str, Any] | None,
) -> None:
    """Surface the human-in-the-loop trace of the turn, when any exists.

    Two sources compose: the streaming-level interrupt of THIS run (the turn
    ended waiting for the user) and the state flags a resumed run carries
    (approval, clarification, FOR_EACH cancellation).

    Args:
        debug_metrics: Debug payload mutated in place.
        state: Final graph state.
        hitl_interrupt: ``{action_type, tool_name}`` captured when this run
            emitted an interrupt, else None.
    """
    state = state or {}
    plan_approved = state.get("plan_approved")
    clarification_response = state.get("clarification_response")
    for_each_cancelled = state.get("for_each_cancelled")
    if not (hitl_interrupt or plan_approved or clarification_response or for_each_cancelled):
        return
    try:
        debug_metrics["hitl"] = {
            "interrupted": bool(hitl_interrupt),
            "interrupt_action_type": (hitl_interrupt or {}).get("action_type"),
            "interrupt_tool_name": (hitl_interrupt or {}).get("tool_name"),
            "plan_approved": bool(plan_approved),
            "clarification_response": clarification_response,
            "clarification_field": state.get("clarification_field"),
            "for_each_cancelled": bool(for_each_cancelled),
            "cancellation_reason": state.get("cancellation_reason"),
        }
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("debug_metrics_hitl_failed", error=str(err))


async def add_interest_detection(
    debug_metrics: dict[str, Any],
    user_id: Any,
    state: dict[str, Any] | None,
    run_id: str,
) -> None:
    """Analyze the current message for interests and add the section.

    Uses ``analyze_interests_for_debug()`` (results cached in Redis, reused
    by the background extraction). Extracted verbatim from
    ``StreamingService._emit_debug_metrics`` (file-size ratchet).

    Args:
        debug_metrics: Debug payload mutated in place.
        user_id: Owner of the conversation (skip when falsy).
        state: Final graph state (messages + user_language).
        run_id: Run id for cache keying and logging.
    """
    if not user_id or not state:
        return
    try:
        from src.core.config import get_settings
        from src.domains.interests.services.extraction_service import (
            analyze_interests_for_debug,
        )

        interest_detection = await analyze_interests_for_debug(
            user_id=user_id,
            messages=state.get("messages", []),
            session_id=run_id,
            user_language=state.get("user_language", get_settings().default_language),
        )
        debug_metrics["interest_profile"] = interest_detection
        logger.debug(
            "debug_metrics_interest_detection_added",
            run_id=run_id,
            enabled=interest_detection.get("enabled", False),
            analyzed=interest_detection.get("analyzed", False),
            extracted_count=len(interest_detection.get("extracted_interests", [])),
        )
    except (ImportError, ValueError, RuntimeError) as interest_err:
        logger.debug(
            "debug_metrics_interest_detection_failed",
            run_id=run_id,
            error=str(interest_err),
            error_type=type(interest_err).__name__,
        )


def add_memory_detection(debug_metrics: dict[str, Any], run_id: str) -> None:
    """Add the memories extracted from the current message (pop-once cache).

    Retrieves debug data cached by ``extract_memories_background()`` which
    has already completed (awaited via ``await_run_id_tasks``). Extracted
    verbatim from ``StreamingService._emit_debug_metrics`` (file-size
    ratchet).

    Args:
        debug_metrics: Debug payload mutated in place.
        run_id: Run whose extraction cache to read.
    """
    if not run_id:
        return
    try:
        from src.domains.agents.services.memory_extractor import (
            get_memory_extraction_debug,
        )

        memory_detection = get_memory_extraction_debug(run_id)
        if memory_detection:
            debug_metrics["memory_detection"] = memory_detection
            logger.debug(
                "debug_metrics_memory_detection_added",
                run_id=run_id,
                enabled=memory_detection.get("enabled", False),
                extracted_count=len(memory_detection.get("extracted_memories", [])),
            )
    except (ImportError, ValueError, RuntimeError) as mem_det_err:
        logger.debug(
            "debug_metrics_memory_detection_failed",
            run_id=run_id,
            error=str(mem_det_err),
            error_type=type(mem_det_err).__name__,
        )


def build_compaction(debug_metrics: dict[str, Any], state: dict[str, Any] | None) -> None:
    """Surface context compaction (count, strategy, tokens saved) when it ran.

    Args:
        debug_metrics: Debug payload mutated in place.
        state: Final graph state carrying ``compaction_*`` keys.
    """
    state = state or {}
    count = int(state.get("compaction_count") or 0)
    debug = state.get("compaction_debug") or {}
    if count <= 0 and not debug:
        return
    try:
        summary = state.get("compaction_summary") or ""
        debug_metrics["compaction"] = {
            "count": count,
            "strategy": debug.get("strategy"),
            "tokens_saved": debug.get("tokens_saved"),
            "duration_ms": debug.get("duration_ms"),
            "messages_removed": debug.get("messages_removed"),
            "summary_preview": summary[:_SUMMARY_PREVIEW_CHARS],
        }
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("debug_metrics_compaction_failed", error=str(err))
