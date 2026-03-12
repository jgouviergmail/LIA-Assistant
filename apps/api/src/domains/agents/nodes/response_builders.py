"""
Response builders for planner node.

Extracted from planner_node.py for maintainability.
These are pure functions that construct state update dictionaries.

Phase 4 - Refactoring: Secure extraction of response builders.
"""

from typing import Any

import structlog

from src.core.field_names import FIELD_PLAN_ID, FIELD_STEP_ID
from src.domains.agents.constants import (
    STATE_KEY_CLARIFICATION_FIELD,
    STATE_KEY_CLARIFICATION_RESPONSE,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_PLANNER_METADATA,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
from src.infrastructure.observability.metrics_agents import (
    planner_plans_created_total,
    planner_plans_rejected_total,
)

logger = structlog.get_logger(__name__)


def build_success_response(
    execution_plan: ExecutionPlan,
    last_validation_result: Any,
    run_id: str,
) -> dict[str, Any]:
    """
    Build success response with plan metadata and validation results.

    Encapsulates all success path logic:
    - Validation summary logging
    - Prometheus metrics tracking
    - Plan cost update
    - Frontend metadata construction
    - State return dictionary

    Args:
        execution_plan: Validated execution plan
        last_validation_result: ValidationResult from PlanValidator
        run_id: Current run ID for logging

    Returns:
        State update dictionary with plan, metadata, and validation result
    """

    # Build detailed validation summary for logs
    validation_summary = {
        "is_valid": last_validation_result.is_valid,
        "total_cost_usd": last_validation_result.total_cost_usd,
        "warnings_count": len(last_validation_result.warnings),
        "errors_count": len(last_validation_result.errors),
    }
    if last_validation_result.warnings:
        validation_summary["warnings"] = [
            {"code": w.code, "message": w.message} for w in last_validation_result.warnings
        ]

    logger.info(
        "planner_plan_validated",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        step_count=len(execution_plan.steps),
        execution_mode=execution_plan.execution_mode,
        validation=validation_summary,
    )

    # Track metrics
    planner_plans_created_total.labels(
        execution_mode=execution_plan.execution_mode,
    ).inc()

    # Update plan with validated cost
    execution_plan.estimated_cost_usd = last_validation_result.total_cost_usd

    # Build detailed steps summary for frontend
    steps_summary = []
    for step in execution_plan.steps:
        step_info = {
            FIELD_STEP_ID: step.step_id,
            "step_type": step.step_type,
        }
        if step.step_type == "TOOL":
            step_info["tool"] = step.tool_name
            step_info["agent"] = step.agent_name
            # Extract voice estimation parameters (limit, max_results, query length)
            if step.parameters:
                voice_params = {}
                # Result count parameters
                for key in ("limit", "max_results", "num_results", "count", "max_items"):
                    if key in step.parameters:
                        voice_params["result_count"] = step.parameters[key]
                        break
                # Query length impacts response verbosity
                if "query" in step.parameters and step.parameters["query"]:
                    voice_params["query_length"] = len(str(step.parameters["query"]))
                # Search vs detail indicator (from tool name pattern)
                if step.tool_name:
                    tool_lower = step.tool_name.lower()
                    if any(k in tool_lower for k in ("search", "list", "find")):
                        voice_params["tool_type"] = "search"
                    elif any(k in tool_lower for k in ("get", "detail", "info", "show")):
                        voice_params["tool_type"] = "detail"
                    else:
                        voice_params["tool_type"] = "other"
                if voice_params:
                    step_info["voice_params"] = voice_params
        elif step.step_type == "CONDITIONAL":
            step_info["condition"] = step.condition
            step_info["on_success"] = step.on_success
            step_info["on_fail"] = step.on_fail
        steps_summary.append(step_info)

    # Build planner metadata for streaming to frontend
    planner_metadata = {
        FIELD_PLAN_ID: execution_plan.plan_id,
        "step_count": len(execution_plan.steps),
        "execution_mode": execution_plan.execution_mode,
        "estimated_cost_usd": last_validation_result.total_cost_usd,
        "steps": steps_summary,
        "validation": {
            "is_valid": last_validation_result.is_valid,
            "warnings_count": len(last_validation_result.warnings),
            "errors_count": len(last_validation_result.errors),
        },
    }

    # Add warnings details if any
    if last_validation_result.warnings:
        planner_metadata["validation"]["warnings"] = [
            {
                "code": w.code.value if hasattr(w.code, "value") else str(w.code),
                "message": w.message,
            }
            for w in last_validation_result.warnings
        ]

    return {
        STATE_KEY_EXECUTION_PLAN: execution_plan,
        STATE_KEY_PLANNER_METADATA: planner_metadata,
        STATE_KEY_PLANNER_ERROR: None,  # Clear any previous error on success
        STATE_KEY_VALIDATION_RESULT: last_validation_result,  # Phase 8: For approval_gate routing
        # Phase 2 OPTIMPLAN - Issue #60: Reset clarification flags after re-planning
        STATE_KEY_NEEDS_REPLAN: False,  # Clear flag to prevent re-routing to planner
        STATE_KEY_CLARIFICATION_RESPONSE: None,  # Clear clarification after use
        STATE_KEY_CLARIFICATION_FIELD: None,  # Clear clarification field after use
    }


def build_validation_failed_response(
    execution_plan: ExecutionPlan,
    last_validation_result: Any,
) -> dict[str, Any]:
    """
    Build error response for validation failures after retries exhausted.

    Args:
        execution_plan: The execution plan that failed validation
        last_validation_result: ValidationResult with errors and warnings

    Returns:
        State update dictionary with error details
    """

    planner_plans_rejected_total.labels(
        reason="validation_failed",
    ).inc()

    # Build error details for frontend streaming
    error_details = []
    for err in last_validation_result.errors:
        error_details.append(
            {
                "severity": "error",
                "code": err.code.value if hasattr(err.code, "value") else str(err.code),
                "message": err.message,
                "step_index": err.step_index,
                "context": err.context if hasattr(err, "context") else None,
            }
        )

    warning_details = []
    for warn in last_validation_result.warnings:
        warning_details.append(
            {
                "severity": "warning",
                "code": warn.code.value if hasattr(warn.code, "value") else str(warn.code),
                "message": warn.message,
                "step_index": warn.step_index,
            }
        )

    # Return error in state for streaming to frontend
    # Note: The "message" field contains the first error's message for display.
    # The i18n formatting ("Plan validation failed: ...") is handled in response_node.py
    # which has access to user_language.
    return {
        STATE_KEY_EXECUTION_PLAN: None,
        STATE_KEY_PLANNER_ERROR: {
            FIELD_PLAN_ID: execution_plan.plan_id,
            "step_count": len(execution_plan.steps),
            "errors": error_details,
            "warnings": warning_details,
            "message": error_details[0]["message"] if error_details else None,
        },
    }


def build_clarification_response(
    execution_plan: ExecutionPlan,
    run_id: str,
) -> dict[str, Any]:
    """
    Build response for clarification request (missing required parameters).

    When the planner detects that a required parameter is missing from the user's
    request, it generates an empty plan with needs_clarification=True and
    missing_parameters describing what information is needed.

    This response triggers the semantic_validation flow with requires_clarification=True,
    which will interrupt execution and ask the user for the missing information.

    Args:
        execution_plan: The (empty) execution plan with clarification metadata
        run_id: Current run ID for logging

    Returns:
        State update dictionary that triggers clarification flow
    """
    from src.domains.agents.orchestration.validator import ValidationResult

    missing_params = execution_plan.metadata.get("missing_parameters", [])
    reasoning = execution_plan.metadata.get("reasoning", "Missing required parameter")

    # Build clarification questions from missing parameters
    clarification_questions = []
    for param in missing_params:
        if isinstance(param, dict):
            question = param.get("question", f"Please provide: {param.get('parameter', 'unknown')}")
            clarification_questions.append(question)
        else:
            clarification_questions.append(f"Please provide: {param}")

    logger.info(
        "planner_clarification_response_built",
        run_id=run_id,
        plan_id=execution_plan.plan_id,
        missing_params_count=len(missing_params),
        clarification_questions=clarification_questions,
    )

    # Create a ValidationResult with requires_hitl=True to trigger routing to semantic_validator
    # The semantic_validator will then see semantic_validation.requires_clarification=True
    # and route to clarification_node
    validation_result = ValidationResult(
        is_valid=True,  # Mark as valid to pass validation check
        requires_hitl=True,  # Force routing through semantic_validator
        total_cost_usd=0.0,
        total_steps=0,
    )

    # Return state that triggers clarification node via semantic_validation
    # The semantic_validation field is used by the graph routing to determine
    # whether to go to clarification_node or approval_gate
    return {
        STATE_KEY_EXECUTION_PLAN: execution_plan,  # Empty plan with metadata
        STATE_KEY_PLANNER_ERROR: None,
        STATE_KEY_VALIDATION_RESULT: validation_result,  # Required for routing to semantic_validator
        STATE_KEY_PLANNER_METADATA: {
            FIELD_PLAN_ID: execution_plan.plan_id,
            "step_count": 0,
            "execution_mode": execution_plan.execution_mode,
            "estimated_cost_usd": 0.0,
            "steps": [],
            "needs_clarification": True,
            "missing_parameters": missing_params,
            "reasoning": reasoning,
        },
        # Trigger clarification flow via semantic_validation state
        # This is used by route_from_semantic_validator to decide next node
        "semantic_validation": {
            "requires_clarification": True,
            "is_valid": False,  # Plan cannot execute without clarification
            "clarification_questions": clarification_questions,
            "issues": [
                {
                    "issue_type": "missing_required_parameter",
                    "description": reasoning,
                    "severity": "high",
                }
            ],
            "confidence": 0.0,
        },
        # FIX: Clear needs_replan to prevent infinite loop in routing
        # Without this, route_from_semantic_validator routes to planner instead of clarification
        # when needs_replan=True was set by approval_gate (REPLAN scenario)
        STATE_KEY_NEEDS_REPLAN: False,
        STATE_KEY_CLARIFICATION_RESPONSE: None,  # Clear any stale clarification
        STATE_KEY_CLARIFICATION_FIELD: None,  # Clear stale clarification field
    }


def build_parsing_failed_response(
    run_id: str,
    execution_plan: ExecutionPlan | None,
    last_validation_result: Any | None,
) -> dict[str, Any]:
    """
    Build error response for parsing failures or unexpected states.

    Args:
        run_id: Current run ID for logging
        execution_plan: The execution plan (may be None if parsing failed)
        last_validation_result: ValidationResult (may be None if parsing failed)

    Returns:
        State update dictionary with generic error
    """
    logger.error(
        "planner_parsing_failed_final",
        run_id=run_id,
        has_execution_plan=execution_plan is not None,
        has_validation_result=last_validation_result is not None,
    )

    # Return generic error (specific error already logged in service)
    return {
        STATE_KEY_EXECUTION_PLAN: None,
        STATE_KEY_PLANNER_ERROR: {
            "message": "Failed to parse or validate execution plan",
        },
    }
