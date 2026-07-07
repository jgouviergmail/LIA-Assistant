"""
Approval Gate Node (Phase 8 - HITL Plan-Level).

Plan-level HITL is now redundant with tool-level HITL: every mutation tool has
its own downstream confirmation (draft_critique for individual actions,
for_each_confirmation for bulk operations). This node is therefore a
pass-through that always approves the plan, avoiding double/triple confirmation.

The node stays wired in the graph (planner -> approval_gate -> task_orchestrator)
so plan-level HITL can be re-enabled later by restoring an interrupt() here
without re-wiring the graph.
"""

from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig

from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# APPROVAL GATE NODE
# ============================================================================


@track_metrics(
    node_name="approval_gate",
    duration_metric=agent_node_duration_seconds,
    counter_metric=agent_node_executions_total,
    log_execution=True,
    log_errors=True,
)
async def approval_gate_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    Approval Gate Node - Plan-Level HITL (pass-through).

    Auto-approves the plan: plan-level HITL is superseded by tool-level HITL
    (draft_critique / for_each_confirmation), so this node passes through to
    avoid double confirmation.

    Métriques trackées automatiquement via @track_metrics:
    - agent_node_executions_total{node_name="approval_gate", status="success/error"}
    - agent_node_duration_seconds{node_name="approval_gate"}

    Args:
        state: État du graph avec execution_plan et validation_result
        config: Configuration LangGraph

    Returns:
        Dict avec plan_approved flag
    """
    # NOTE: Tool approval is always enabled (no kill switch)

    # =========================================================================
    # BUG FIX 2025-12-07: Skip if plan_approved already True (from clarification)
    # =========================================================================
    # When user confirms a destructive operation via clarification_node, it sets
    # plan_approved=True. We should NOT ask for another approval in approval_gate.
    # Without this, the user would be asked to confirm TWICE (once in clarification,
    # once in approval_gate), which is confusing UX.
    # =========================================================================
    existing_plan_approved = state.get(STATE_KEY_PLAN_APPROVED)
    if existing_plan_approved is True:
        logger.info(
            "approval_gate_plan_already_approved",
            plan_approved=True,
            msg="Plan already approved (from clarification), skipping HITL interrupt",
        )
        # Return without changes - plan_approved is already True
        result_already_approved: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: True}
        track_state_updates(state, result_already_approved, "approval_gate")
        return result_already_approved

    # Extract data from state
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
    validation_result = state.get(STATE_KEY_VALIDATION_RESULT)

    if not execution_plan:
        logger.error("approval_gate_no_execution_plan")
        result_no_plan: dict[str, Any] = {
            STATE_KEY_PLAN_APPROVED: False,
            STATE_KEY_PLAN_REJECTION_REASON: "No execution plan in state",
        }
        track_state_updates(state, result_no_plan, "approval_gate")
        return result_no_plan

    if not validation_result:
        logger.warning(
            "approval_gate_no_validation_result",
            msg="No validation result, assuming approval not required",
        )
        result_no_validation: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: True}
        track_state_updates(state, result_no_validation, "approval_gate")
        return result_no_validation

    # Check if approval required
    # Plan-level HITL is now redundant: every mutation tool has its own
    # downstream HITL (draft_critique for individual actions, for_each_confirmation
    # for bulk operations). Auto-approve to avoid double/triple confirmation.
    if not validation_result.requires_hitl:
        logger.info(
            "approval_gate_passthrough",
            plan_id=execution_plan.plan_id,
            msg="Plan does not require approval, passing through",
        )
    else:
        logger.info(
            "approval_gate_auto_approved",
            plan_id=execution_plan.plan_id,
            msg="Plan-level HITL skipped — downstream HITL (for_each/draft_critique) will handle confirmation",
        )
    result_passthrough: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: True}
    track_state_updates(state, result_passthrough, "approval_gate", execution_plan.plan_id)
    return result_passthrough
