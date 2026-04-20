"""
Clarification Node - HITL node for semantic validation clarification.

This module provides a LangGraph node that interrupts execution when semantic
validation detects ambiguities or issues requiring user clarification.

Architecture:
    SemanticValidator → ClarificationNode → interrupt() → User clarifies
    → Command(resume=response) → Planner regenerates plan

Pattern: LangGraph v1.0 interrupt()
    - interrupt() suspends workflow and saves checkpoint
    - Frontend sends Command(resume={...}) to continue
    - State is updated with clarification_response

Usage in Graph:
    graph.add_node("clarification", clarification_node)
    graph.add_conditional_edges(
        "semantic_validator",
        lambda state: "clarification" if state.get("semantic_validation", {}).get("requires_clarification") else "approval_gate"
    )

References:
    - OPTIMPLAN/PLAN.md: Section 4 - Phase 2
    - approval_gate_node.py: Similar interrupt pattern
    - semantic_validator.py: Validation logic

Created: 2025-11-25
"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.domains.agents.constants import (
    STATE_KEY_CLARIFICATION_FIELD,
    STATE_KEY_CLARIFICATION_RESPONSE,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def clarification_node(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    LangGraph node for semantic validation clarification.

    This node interrupts execution when semantic validation detects issues
    requiring user clarification. The interrupt allows the frontend to:
    1. Display clarification questions to the user
    2. Collect user response
    3. Resume execution with Command(resume={...})

    The node uses the HITL streaming infrastructure (HitlInteractionRegistry)
    to stream clarification questions progressively (TTFT < 500ms).

    Args:
        state: LangGraph state dict containing:
            - semantic_validation: SemanticValidationResult (or dict)
            - user_language: Language code (fr, en, es)
        config: Optional RunnableConfig for LangGraph

    Returns:
        Dict with state updates:
            - clarification_response: User's clarification (from Command resume)
            - needs_replan: True (triggers planner regeneration)
            - planner_iteration: Incremented iteration counter

    Raises:
        None: Errors are logged but don't block execution

    Example State Flow:
        >>> # Before clarification
        >>> state = {
        ...     "semantic_validation": {
        ...         "requires_clarification": True,
        ...         "clarification_questions": ["Voulez-vous UN ou TOUS les contacts ?"],
        ...         "issues": [{"type": "cardinality_mismatch", ...}],
        ...     },
        ...     "user_language": "fr",
        ... }
        >>>
        >>> # After interrupt + Command(resume={"clarification": "All contacts"})
        >>> new_state = await clarification_node(state, config)
        >>> new_state["clarification_response"]  # "All contacts"
        >>> new_state["needs_replan"]  # True

    Notes:
        - This node ONLY executes if semantic_validation.requires_clarification=True
        - Frontend must handle hitl_interrupt_metadata event with type="clarification"
        - Planner must incorporate clarification_response in regeneration prompt
    """
    # Extract semantic validation result
    semantic_validation = state.get("semantic_validation")
    user_language = state.get("user_language", "fr")

    # Safety check: Only proceed if clarification is required
    if not semantic_validation:
        logger.warning(
            "clarification_node_called_without_semantic_validation",
            has_semantic_validation=False,
        )
        return state  # No-op

    # Convert to dict-like access depending on type
    # Supports: Pydantic models, Python dataclasses, plain dicts
    if hasattr(semantic_validation, "model_dump"):
        # Pydantic model
        validation_dict = semantic_validation.model_dump()
    elif hasattr(semantic_validation, "__dataclass_fields__"):
        # Python dataclass - convert to dict for consistent access
        from dataclasses import asdict

        validation_dict = asdict(semantic_validation)
    elif isinstance(semantic_validation, dict):
        validation_dict = semantic_validation
    else:
        # Unknown type - try dict-like access, fallback to empty
        validation_dict = semantic_validation if hasattr(semantic_validation, "get") else {}

    requires_clarification = validation_dict.get("requires_clarification", False)

    if not requires_clarification:
        logger.debug(
            "clarification_node_skipped_no_clarification_required",
            requires_clarification=False,
        )
        return state  # No-op

    # Extract clarification questions, semantic issues, and field being asked for
    clarification_questions = validation_dict.get("clarification_questions", [])
    issues = validation_dict.get("issues", [])
    clarification_field = validation_dict.get("clarification_field")  # e.g., "subject", "body"

    logger.info(
        "clarification_node_triggering_interrupt",
        question_count=len(clarification_questions),
        issue_count=len(issues),
        user_language=user_language,
    )

    # Track clarification request (dashboard 08 HITL Clarification Requests panel)
    try:
        from src.infrastructure.observability.metrics_agents import (
            hitl_clarification_requests_total,
        )

        reason = "semantic_validation"
        if issues:
            first_issue = issues[0]
            if isinstance(first_issue, dict):
                reason = first_issue.get("issue_type", reason)
            elif hasattr(first_issue, "issue_type"):
                reason = first_issue.issue_type
        hitl_clarification_requests_total.labels(reason=str(reason)).inc()
    except Exception:
        pass

    # Prepare interrupt payload
    # Format compatible with HITL streaming infrastructure
    # StreamingService will use ClarificationInteraction for streaming

    # Process issues - can be: empty list, list of strings, or list of dicts/objects
    # From planner missing_parameters: issues may be strings like "missing_parameter"
    # From SemanticValidator: issues are SemanticIssue objects or dicts with issue_type, description, severity
    semantic_issues = []
    for issue in issues:
        if isinstance(issue, str):
            # Simple string issue (e.g., from planner missing parameters)
            semantic_issues.append(
                {
                    "type": issue,
                    "description": issue,
                    "severity": "medium",
                }
            )
        elif isinstance(issue, dict):
            # Dict issue - extract type carefully (may be nested or direct)
            issue_type = issue.get("issue_type", "unknown")
            if isinstance(issue_type, dict):
                issue_type = issue_type.get("value", "unknown")
            elif hasattr(issue_type, "value"):
                issue_type = issue_type.value
            semantic_issues.append(
                {
                    "type": issue_type,
                    "description": issue.get("description", ""),
                    "severity": issue.get("severity", "medium"),
                }
            )
        elif hasattr(issue, "issue_type"):
            # Object with issue_type attribute (e.g., SemanticIssue)
            issue_type = issue.issue_type
            if hasattr(issue_type, "value"):
                issue_type = issue_type.value
            semantic_issues.append(
                {
                    "type": issue_type,
                    "description": getattr(issue, "description", ""),
                    "severity": getattr(issue, "severity", "medium"),
                }
            )
        else:
            # Unknown type - convert to string
            semantic_issues.append(
                {
                    "type": str(issue),
                    "description": str(issue),
                    "severity": "medium",
                }
            )

    interrupt_payload = {
        "action_requests": [
            {
                "type": "clarification",
                "clarification_questions": clarification_questions,
                "semantic_issues": semantic_issues,
            }
        ],
        # Phase 1 HITL Streaming: Enable streaming question generation
        "generate_question_streaming": True,
        "user_language": user_language,
    }

    # Trigger interrupt - workflow pauses until Command(resume=...)
    # Frontend receives interrupt via SSE, displays clarification questions
    # User responds, frontend sends Command(resume={"clarification": "..."})
    clarification_data = interrupt(interrupt_payload)

    # Extract clarification response from Command resume data
    # clarification_data structure depends on frontend implementation
    # Expected: {"clarification": "user response text"}
    clarification_response = (
        clarification_data.get("clarification", "")
        if isinstance(clarification_data, dict)
        else str(clarification_data)
    )

    logger.info(
        "clarification_node_received_user_response",
        clarification_response_length=len(clarification_response),
        has_response=bool(clarification_response),
    )

    # Track metrics
    from src.infrastructure.observability.metrics_agents import (
        semantic_validation_clarification_requests,
    )

    semantic_validation_clarification_requests.inc()

    # Return state updates
    # planner_iteration prevents infinite clarification loops (max: PLANNER_MAX_REPLANS setting)
    #
    # CRITICAL: We must set requires_clarification=False to signal that the clarification
    # has been received. This prevents semantic_validator_node from re-routing to clarification.
    updated_semantic_validation = dict(validation_dict)
    updated_semantic_validation["requires_clarification"] = False
    # Clear clarification questions as they've been answered
    updated_semantic_validation["clarification_questions"] = []

    # =========================================================================
    # BUG FIX 2025-12-07: Differentiate between confirmation vs info clarification
    # =========================================================================
    # Issue: When user confirms a destructive operation ("ok"), the system was
    # setting needs_replan=True, causing:
    # 1. Planner regenerates the SAME plan
    # 2. Semantic validator detects SAME dangerous_ambiguity
    # 3. Routes to clarification again → INFINITE LOOP (recursion limit hit)
    #
    # Fix: For "confirmation-only" issues (DANGEROUS_AMBIGUITY, IMPLICIT_ASSUMPTION),
    # user's "ok" means "proceed with existing plan", NOT "regenerate plan".
    # - Confirmation issues: needs_replan=False, plan_approved=True → execute
    # - Info issues (missing_parameter, cardinality): needs_replan=True → replanner
    # =========================================================================

    # Issue types that only need user CONFIRMATION (not new info)
    # For these, user's "ok" means "proceed" not "regenerate"
    CONFIRMATION_ONLY_ISSUES = {
        "dangerous_ambiguity",
        "implicit_assumption",
        # Add SemanticIssueType enum values for safety
        "DANGEROUS_AMBIGUITY",
        "IMPLICIT_ASSUMPTION",
    }

    # Check if ALL issues are confirmation-only
    all_confirmation_only = True
    for issue in issues:
        if isinstance(issue, str):
            issue_type = issue
        elif isinstance(issue, dict):
            issue_type = issue.get("issue_type", issue.get("type", ""))
            if isinstance(issue_type, dict):
                issue_type = issue_type.get("value", "")
            elif hasattr(issue_type, "value"):
                issue_type = issue_type.value
        elif hasattr(issue, "issue_type"):
            issue_type = issue.issue_type
            if hasattr(issue_type, "value"):
                issue_type = issue_type.value
        else:
            issue_type = str(issue)

        if issue_type not in CONFIRMATION_ONLY_ISSUES:
            all_confirmation_only = False
            break

    # Determine if we need replanning or just approval
    if all_confirmation_only and issues:
        # User confirmed a destructive/assumption-based operation
        # The plan is correct, just proceed with execution
        logger.info(
            "clarification_node_confirmation_only",
            issue_types=[
                (issue.get("issue_type") if isinstance(issue, dict) else str(issue))
                for issue in issues[:3]
            ],
            clarification_response=clarification_response[:50] if clarification_response else None,
            action="Proceeding to execution (no replan needed)",
        )

        # =========================================================================
        # BUG FIX 2026-01-14: Do NOT increment planner_iteration for user clarifications
        # =========================================================================
        # planner_iteration is a protection against AUTO-REPLAN infinite loops
        # (semantic_validator detects issues → planner auto-corrects → repeat).
        # User clarifications are NOT auto-replans - they provide new information.
        # Incrementing here caused max_iterations bypass after 2 clarifications,
        # preventing email flow from asking for body (to → subject → BYPASS).
        # Only semantic_validator_node should increment for auto-replans.
        # =========================================================================
        return {
            STATE_KEY_CLARIFICATION_RESPONSE: clarification_response,
            STATE_KEY_CLARIFICATION_FIELD: clarification_field,  # Field that was asked for
            STATE_KEY_NEEDS_REPLAN: False,  # No need to regenerate plan
            STATE_KEY_PLAN_APPROVED: True,  # User confirmed, proceed to execution
            # NOTE: planner_iteration NOT incremented - user clarifications don't count
            STATE_KEY_SEMANTIC_VALIDATION: updated_semantic_validation,
        }
    else:
        # User provided new info (missing parameter, cardinality correction, etc.)
        # Need to regenerate plan with the new info
        logger.info(
            "clarification_node_needs_replan",
            issue_types=[
                (issue.get("issue_type") if isinstance(issue, dict) else str(issue))
                for issue in issues[:3]
            ],
            clarification_response=clarification_response[:50] if clarification_response else None,
            action="Routing to planner for regeneration",
        )

        # =========================================================================
        # BUG FIX 2026-01-14: Do NOT increment planner_iteration for user clarifications
        # =========================================================================
        # Same reasoning as confirmation-only path above. User providing missing
        # parameter (to, subject, body) is NOT an auto-replan attempt.
        # =========================================================================
        return {
            STATE_KEY_CLARIFICATION_RESPONSE: clarification_response,
            STATE_KEY_CLARIFICATION_FIELD: clarification_field,  # Field that was asked for
            STATE_KEY_NEEDS_REPLAN: True,  # Regenerate plan with user's new info
            # NOTE: planner_iteration NOT incremented - user clarifications don't count
            STATE_KEY_SEMANTIC_VALIDATION: updated_semantic_validation,
        }
