"""FOR_EACH bulk-confirmation HITL node — replay-safe single-pass (2026-07).

Historically the FOR_EACH confirmation lived inside task_orchestrator as a
while-loop around ``interrupt()``: on every resume LangGraph re-executed the
whole node, re-running the provider pre-execution (real API calls — latency,
quota, and the previews shown could diverge from the items executed) and
re-running every past LLM item-filter call (non-deterministic).

The loop now lives here as a dedicated node, one ``interrupt()`` per node
execution, mirroring the draft-critique design (hitl_dispatch_node):

- task_orchestrator pre-executes the providers ONCE, returns the
  ``for_each_hitl_ctx`` state update (checkpointed) and routes here;
- APPROVE  → ``ctx.approved = True`` → route back to task_orchestrator, which
  resumes execution from the persisted context (no re-fetch);
- REJECT   → cancel result (identical keys to the historical
  ``_build_cancel_result``) → routes to initiative/response;
- EDIT     → the LLM item filter runs ONCE, the filtered previews and the
  cumulative ``filtered_indices`` are persisted in the ctx → self-loop; the
  next interrupt presents the filtered list, and a later resume replays
  nothing but the current interrupt.

Invariant: the item list the user last saw is EXACTLY the list executed.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import resolve_language
from src.domains.agents.constants import (
    HITL_DECISION_APPROVE,
    HITL_DECISION_EDIT,
    HITL_DECISION_REJECT,
    NODE_FOR_EACH_CONFIRM,
    STATE_KEY_FOR_EACH_CANCELLATION_REASON,
    STATE_KEY_FOR_EACH_CANCELLED,
    STATE_KEY_FOR_EACH_HITL_CTX,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.for_each_preview_identity import (
    approved_preview_context,
    resolve_item_preview_indices,
    selection_matches_snapshot,
    snapshot_preview_identity,
)
from src.domains.agents.services.hitl.item_filter import get_item_filter_service
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    hitl_for_each_approval_latency,
    hitl_for_each_decisions,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)

STATE_KEY_AGENT_RESULTS = "agent_results"
STATE_KEY_DRAFT_ACTION_RESULT = "draft_action_result"


def _cancel_result(reason: str) -> dict[str, Any]:
    """Cancellation state update — identical keys to the historical
    task_orchestrator ``_build_cancel_result`` (response_node handles it like
    a HITL draft cancel), plus the ctx purge."""
    return {
        STATE_KEY_AGENT_RESULTS: {},
        STATE_KEY_FOR_EACH_CANCELLED: True,
        STATE_KEY_FOR_EACH_CANCELLATION_REASON: reason,
        STATE_KEY_DRAFT_ACTION_RESULT: {
            "action": "cancel",
            "draft_id": "",
            "draft_type": "for_each_bulk",
            "reason": reason,
        },
        STATE_KEY_FOR_EACH_HITL_CTX: None,
    }


def _approval_result(ctx: dict[str, Any], iteration: int) -> dict[str, Any]:
    approved_ctx = approved_preview_context(ctx)
    decision = "confirm" if approved_ctx["approved"] else "edit"
    hitl_for_each_decisions.labels(decision=decision).inc()
    logger.info(
        "for_each_hitl_approval_checked",
        run_id=ctx.get("run_id", "unknown"),
        plan_id=ctx.get("plan_id", "unknown"),
        iteration=iteration,
        approved=approved_ctx["approved"],
        final_item_count=ctx.get("total_affected"),
    )
    return {STATE_KEY_FOR_EACH_HITL_CTX: {**approved_ctx, "iteration": iteration}}


@trace_node(NODE_FOR_EACH_CONFIRM)
@track_metrics(
    node_name=NODE_FOR_EACH_CONFIRM,
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
)
async def for_each_confirm_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Present the FOR_EACH bulk confirmation and process ONE user decision.

    Args:
        state: Graph state carrying ``for_each_hitl_ctx`` (written by
            task_orchestrator before routing here).
        config: LangGraph configuration.

    Returns:
        State update: approved ctx (back to orchestrator), updated ctx
        (self-loop after an edit), or a cancel result.
    """
    ctx = state.get(STATE_KEY_FOR_EACH_HITL_CTX)
    if not ctx:
        # Defensive: routed here without context — nothing to confirm.
        logger.warning("for_each_confirm_no_context")
        return {}

    result: dict[str, Any]

    run_id = ctx.get("run_id", "unknown")
    plan_id = ctx.get("plan_id", "unknown")
    iteration = int(ctx.get("iteration", 0)) + 1  # 1-based for logs/payload
    max_edit_iterations = settings.api_max_items_per_request

    item_previews: list[dict[str, Any]] = ctx.get("item_previews") or []
    total_affected = int(ctx.get("total_affected", len(item_previews)))

    # ---- Guard: max iterations without approval → safety cancel ----
    if ctx.get("iteration", 0) >= max_edit_iterations:
        hitl_for_each_decisions.labels(decision="cancel").inc()
        logger.warning(
            "for_each_hitl_max_iterations",
            run_id=run_id,
            plan_id=plan_id,
            max_iterations=max_edit_iterations,
        )
        result = _cancel_result("Max HITL iterations reached")
        track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
        return result

    # ---- ONE interrupt per node execution (replay-safety backbone) ----
    interrupt_payload = {
        "action_requests": [
            {
                "type": HitlInteractionType.FOR_EACH_CONFIRMATION.value,
                "plan_id": plan_id,
                "steps": ctx.get("steps", []),
                "total_affected": total_affected,
                "item_previews": item_previews,
                "iteration": iteration,
            }
        ],
        "generate_question_streaming": True,
        "user_language": resolve_language(state.get("user_language")),
        "user_timezone": state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE),
    }

    hitl_start_time = time.time()
    decision_data = interrupt(interrupt_payload)
    hitl_for_each_approval_latency.observe(time.time() - hitl_start_time)

    if not decision_data:
        hitl_for_each_decisions.labels(decision="cancel").inc()
        logger.warning(
            "for_each_hitl_no_decision", run_id=run_id, plan_id=plan_id, iteration=iteration
        )
        result = _cancel_result("No user decision received")
        track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
        return result

    decision = decision_data.get("decision", HITL_DECISION_REJECT)

    # ---- APPROVE: hand the persisted context back to the orchestrator ----
    if decision == HITL_DECISION_APPROVE:
        result = _approval_result(ctx, iteration)
        track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
        return result

    # ---- REJECT: cancel the bulk operation ----
    if decision == HITL_DECISION_REJECT:
        hitl_for_each_decisions.labels(decision="cancel").inc()
        logger.info("for_each_hitl_cancelled", run_id=run_id, plan_id=plan_id, iteration=iteration)
        reason = decision_data.get("rejection_reason", "User cancelled bulk operation")
        result = _cancel_result(reason)
        track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
        return result

    # ---- EDIT: run the LLM item filter ONCE, persist, self-loop ----
    if decision == HITL_DECISION_EDIT:
        hitl_for_each_decisions.labels(decision="edit").inc()
        exclude_criteria = decision_data.get("exclude_criteria", "")

        if not exclude_criteria:
            logger.warning(
                "for_each_edit_no_criteria", run_id=run_id, plan_id=plan_id, iteration=iteration
            )
            # Self-loop: re-present the same items
            result = {STATE_KEY_FOR_EACH_HITL_CTX: {**ctx, "iteration": iteration}}
            track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
            return result

        filter_service = get_item_filter_service()
        try:
            identity_snapshot = snapshot_preview_identity(ctx)
            original_indices = resolve_item_preview_indices(identity_snapshot)
            if original_indices is None:
                raise ValueError("Unproven preview identity")
            indices_to_keep = await filter_service.filter(
                item_previews=identity_snapshot["item_previews"],
                exclude_criteria=exclude_criteria,
                run_id=run_id,
            )
            if not selection_matches_snapshot(
                indices_to_keep, len(item_previews), identity_snapshot, ctx
            ):
                raise ValueError("Invalid preview selection")
        except Exception as filter_error:
            logger.error(
                "for_each_edit_filter_error",
                run_id=run_id,
                error=str(filter_error),
                error_type=type(filter_error).__name__,
            )
            # Self-loop: re-present the same items
            result = {STATE_KEY_FOR_EACH_HITL_CTX: {**ctx, "iteration": iteration}}
            track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
            return result

        filtered_previews = [item_previews[i] for i in indices_to_keep]

        if not filtered_previews:
            hitl_for_each_decisions.labels(decision="cancel").inc()
            logger.info(
                "for_each_edit_all_excluded",
                run_id=run_id,
                plan_id=plan_id,
                exclude_criteria_length=len(exclude_criteria),
                original_count=len(item_previews),
            )
            result = _cancel_result("All items excluded by user filter")
            track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
            return result

        # Every position is relative to the displayed list, never the source list.
        filtered_indices = [original_indices[i] for i in indices_to_keep]

        logger.info(
            "for_each_edit_items_filtered",
            run_id=run_id,
            plan_id=plan_id,
            iteration=iteration,
            original_count=len(item_previews),
            filtered_count=len(filtered_previews),
            exclude_criteria_length=len(exclude_criteria),
        )

        # Self-loop: the filtered list is persisted (and checkpointed) BEFORE
        # the next interrupt — this filter call will never be re-run on resume.
        result = {
            STATE_KEY_FOR_EACH_HITL_CTX: {
                **ctx,
                "item_previews": filtered_previews,
                "item_preview_indices": filtered_indices,
                "total_affected": len(filtered_previews),
                "filtered_indices": filtered_indices,
                "iteration": iteration,
            }
        }
        track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
        return result

    # ---- Unknown decision: cancel for safety ----
    hitl_for_each_decisions.labels(decision="cancel").inc()
    logger.warning(
        "for_each_hitl_unknown_decision",
        run_id=run_id,
        plan_id=plan_id,
        decision=decision,
        iteration=iteration,
    )
    result = _cancel_result(f"Unknown decision: {decision}")
    track_state_updates(state, result, NODE_FOR_EACH_CONFIRM, run_id)
    return result
