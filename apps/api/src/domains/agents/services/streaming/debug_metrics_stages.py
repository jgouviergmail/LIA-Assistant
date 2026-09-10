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


def _react_exit_reason(result: dict[str, Any]) -> str | None:
    """Why a ReAct loop stopped, as the panel states it.

    Args:
        result: ``react_agent_result`` from the final state, or ``{}``.

    Returns:
        The stop condition verbatim when the loop was cut short; ``"answered"``
        when it finished on its own — no truncation is not « unknown », the
        model stopped calling tools, which is the loop ending as intended; and
        None when the turn produced no result at all, because an interrupted
        turn never reaches the node that decides this, and claiming
        ``"answered"`` there would be a claim nobody verified.
    """
    truncation = result.get("truncation")
    if isinstance(truncation, dict) and truncation.get("reason"):
        return str(truncation["reason"])
    return "answered" if result else None


def _react_bounds(state: dict[str, Any]) -> dict[str, Any]:
    """What governed the loop, and how it ended (B8).

    Extracted from :func:`build_react_execution` so that function stays under
    the complexity cap while saying strictly more than it used to.

    Args:
        state: Final graph state.

    Returns:
        The bounds and the verdict, ready to merge into the section.
    """
    from src.core.config import get_settings
    from src.domains.agents.utils.react_budget import react_iteration_budget

    ceiling = int(get_settings().react_agent_max_iterations)
    # The bound the loop ACTUALLY stops at. The section used to publish the
    # ceiling alone, so a turn narrowed to four iterations by ADR-238 read as
    # « 4/25 » and looked like a model that gave up — ADR-184's trap (an
    # enforced bound the reader cannot see) pointed at the panel.
    result = state.get("react_agent_result")
    result = result if isinstance(result, dict) else {}
    return {
        "max_iterations": ceiling,
        "iteration_budget": react_iteration_budget(state),  # type: ignore[arg-type]
        "iteration_ceiling": ceiling,
        # ADR-238's allowance BEFORE any extension: with the budget beside it, a
        # reader sees a loop that EARNED more rather than a number that changed
        # on its own.
        "starting_budget": int(state.get("react_max_iterations_effective") or ceiling),
        # ADR-248: the loop buys iterations with results, not with promises.
        "productive_iterations": int(state.get("react_productive_iterations") or 0),
        # WHY it stopped, from the ONE predicate that decided it (resolved once
        # in `react_finalize_node`, so the banner, the tool results the model is
        # given and this line cannot disagree).
        "exit_reason": _react_exit_reason(result),
        # The capabilities the turn asked for and never got: the signal that
        # says whether the budget is CALIBRATED, not merely that it was hit. It
        # only ever reached a log line before.
        "abandoned_calls": list(result.get("abandoned_calls") or []),
    }


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
            **_react_bounds(state),
            "elapsed_seconds": float(state.get("react_elapsed_seconds") or 0.0),
            # ADR-256: the delegated half of the turn, and the bound that
            # governs it. Published next to the value it constrains (ADR-184) —
            # an enforced limit the reader cannot see is a trap, and "elapsed"
            # alone used to read as the turn's total while excluding every
            # second spent inside a tool.
            "tool_seconds": float(state.get("react_tool_seconds") or 0.0),
            "tool_budget_seconds": get_settings().react_tool_budget_seconds,
            "tool_names": list(state.get("react_tool_names") or []),
            "executed_tool_calls": len(state.get("react_call_digests") or {}),
            # ADR-249 — the code the model wrote. It never reaches the ANSWER;
            # it reaches the debug panel, which a superuser opens directly and
            # anyone else only behind TWO switches (the operator's
            # `debug_panel_user_access_enabled` and their own). Saying « admin
            # only » here overstated a gate that does not exist.
            "scripts": list(state.get("react_scripts") or []),
        }
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("debug_metrics_react_execution_failed", error=str(err))


def build_context_window(debug_metrics: dict[str, Any]) -> None:
    """Say how much room the turn actually had, and when compaction would fire.

    ``token_budget`` published four instance-wide thresholds read from settings,
    independent of the model actually configured: a turn could sit in a « safe »
    zone whose ceiling was larger than its model's whole window. The two numbers
    that decide what happens to a long conversation are the slot's EFFECTIVE
    window (ADR-278) and the instant compaction fires — the second being the
    first times a ratio unless an operator pinned an absolute value.

    Both are published beside the value they constrain (ADR-184), and the
    window NAMES the source that answered: one that came from the
    hand-maintained table is a default, not a measurement.

    Enriches the existing block in place; writes nothing when the token budget
    failed to build, because a block invented there would claim room nobody
    measured.

    Args:
        debug_metrics: Debug payload mutated in place.
    """
    budget = debug_metrics.get("token_budget")
    if not isinstance(budget, dict):
        return
    try:
        from src.core.config import settings as app_settings
        from src.core.llm_config_helper import resolve_context_window_for_slot

        # The slot that carries the conversation — the same number compaction,
        # the ReAct budget and the summarisation middleware all read.
        window = resolve_context_window_for_slot("response")
        absolute = int(getattr(app_settings, "compaction_token_threshold", 0) or 0)
        ratio = float(getattr(app_settings, "compaction_threshold_ratio", 0.0) or 0.0)
        threshold = absolute if absolute > 0 else int(window.tokens * ratio)

        used = int(budget.get("current_tokens") or 0)
        budget["context_window"] = window.tokens
        budget["context_window_source"] = window.source
        budget["context_window_model"] = window.model
        # Never a division by an unknown: a percentage invented from a missing
        # count is a figure nobody measured.
        budget["context_used_percent"] = (
            round(used / window.tokens * 100) if window.tokens > 0 and used > 0 else 0
        )
        budget["compaction_threshold"] = threshold
        budget["compaction_threshold_source"] = "absolute" if absolute > 0 else "ratio"
        budget["compaction_threshold_ratio"] = ratio
    except (AttributeError, TypeError, ValueError, ZeroDivisionError) as err:
        logger.debug("debug_metrics_context_window_failed", error=str(err))


def _draft_trace(state: dict[str, Any], draft_result: dict[str, Any] | None) -> dict[str, Any]:
    """WHICH draft a person acted on, and what became of it (B8).

    Two runs of the same tool on different content were indistinguishable, and
    an edit loop that went round three times looked exactly like one that went
    round once.

    Args:
        state: Final graph state.
        draft_result: ``draft_action_result``, or None.

    Returns:
        The draft's identity — never its content.
    """
    result = draft_result or {}
    return {
        "draft_type": result.get("draft_type"),
        "draft_id": result.get("draft_id"),
        "draft_action": result.get("action"),
        # The handle that says « the person approved THIS » — the same digest
        # the pre-approval replay compares. The CONTENT never comes: it holds
        # recipients, subjects and bodies, and the digest answers the
        # correlation question without answering that one (ADR-263's privacy
        # line, applied to the panel — which is not admin-only, so the cheaper
        # answer is the right one).
        "draft_digest": _draft_identity(draft_result),
        "draft_edit_iterations": int(state.get("draft_edit_iteration") or 0),
        "draft_clarification_question": state.get("draft_clarification_question"),
    }


def _draft_identity(draft_result: dict[str, Any] | None) -> str | None:
    """Digest of the draft content a person acted on, or None (B8).

    Args:
        draft_result: ``draft_action_result`` from the state, or None.

    Returns:
        The same digest the HITL binding and the pre-approval replay use, so
        « the person approved THIS » is one identity across all three. None
        when no content was carried — never an empty-content digest, which
        would look like a real identity.
    """
    content = (draft_result or {}).get("draft_content")
    if not isinstance(content, dict) or not content:
        return None
    from src.domains.agents.effects.digest import draft_digest

    return draft_digest(content)


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
    draft_result = state.get("draft_action_result")
    draft_result = draft_result if isinstance(draft_result, dict) else None
    # A confirmed draft with no interrupt and no plan approval used to produce
    # NO section at all: the one turn where a person actually acted was the one
    # the panel said nothing about.
    if not (
        hitl_interrupt
        or plan_approved
        or clarification_response
        or for_each_cancelled
        or draft_result
    ):
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
            **_draft_trace(state, draft_result),
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


async def add_performed_effects(debug_metrics: dict[str, Any], run_id: str) -> None:
    """Add what the turn actually PERFORMED, read back from the register (ADR-263).

    An async stage rather than a section of ``DebugMetricsBuilder``: that
    builder does no I/O at all, and a database read inside it would break the
    property that makes it cheap and testable.

    What an admin sees here is the register's own answer — the same rows the
    user's action journal shows and the same rows the export carries — so the
    debug panel cannot disagree with the record.

    Args:
        debug_metrics: Debug payload mutated in place.
        run_id: The run whose effects to read.
    """
    if not run_id:
        return
    from src.domains.agents.effects.turn_summary import performed_effects

    entries = await performed_effects(run_id)
    debug_metrics["performed_effects"] = {
        "entries": entries,
        "count": len(entries),
        "failed_count": sum(1 for entry in entries if entry.get("status") == "failed"),
    }


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
