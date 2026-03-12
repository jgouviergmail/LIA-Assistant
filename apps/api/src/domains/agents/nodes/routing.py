"""
Fonctions de routing pour le graph d'agents.

Ce module centralise les fonctions de routing conditionnelles utilisées
dans le graph pour déterminer les transitions entre nœuds.

Updated: 2026-01-11 - Added replanned plan validation enforcement
"""

from typing import Literal

import structlog

from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.constants import (
    NODE_APPROVAL_GATE,
    NODE_CLARIFICATION,
    NODE_PLANNER,
    NODE_RESPONSE,
    NODE_SEMANTIC_VALIDATOR,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_REPLAN_INSTRUCTIONS,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.models import MessagesState
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_conditional_edges_total,
    langgraph_node_transitions_total,
)

logger = structlog.get_logger(__name__)


def route_from_planner(
    state: MessagesState,
) -> Literal["approval_gate", "task_orchestrator", "response"]:
    """
    Route depuis le planner vers approval_gate, task_orchestrator, ou response.

    Route vers response si:
    - Le planner n'a pas généré de plan valide (step_count == 0)
    - Cas: requête conversationnelle qui a échappé au routing initial, ou
           aucun outil applicable pour la requête

    Route vers approval_gate (→ semantic_validator) si:
    1. validation_result.requires_hitl = True (mutations avec hitl_required dans manifests)
    2. Plan multi-domaines (> 1 domain) → complexité nécessitant validation sémantique

    Le semantic_validator valide la cohérence sémantique des plans complexes:
    - CARDINALITY_MISMATCH: "tous mes contacts" → plan qui n'en traite qu'un
    - SCOPE_OVERFLOW/UNDERFLOW: plan qui fait plus/moins que demandé
    - DANGEROUS_AMBIGUITY: action risquée sur input vague
    - GHOST_DEPENDENCY: référence à un step inexistant

    Note: Le critère multi-step simple (search→details dans 1 domain) n'est PAS
    inclus car ce pattern est très courant et ne nécessite pas de validation LLM.
    Seul multi-domain déclenche la validation car il implique une vraie complexité
    (coordination entre domaines, potentielle ambiguïté sur les entités).

    Args:
        state: État du graph avec validation_result et query_intelligence

    Returns:
        "response" si pas de plan valide,
        "approval_gate" si validation sémantique requise,
        sinon "task_orchestrator"
    """
    validation_result = state.get(STATE_KEY_VALIDATION_RESULT)
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)

    plan_id = execution_plan.plan_id if execution_plan else None
    step_count = len(execution_plan.steps) if execution_plan and execution_plan.steps else 0

    # === STEP 0: Check for early clarification (before plan exists) ===
    # If planner set semantic_validation.requires_clarification=True without generating
    # a plan (early insufficient content detection), route to semantic_validator
    # which will forward to clarification_node.
    semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)
    if semantic_validation:
        requires_clarification = (
            semantic_validation.get("requires_clarification", False)
            if isinstance(semantic_validation, dict)
            else getattr(semantic_validation, "requires_clarification", False)
        )
        if requires_clarification:
            logger.info(
                "route_from_planner_early_clarification",
                plan_id=plan_id,
                step_count=step_count,
                reason="Early insufficient content detection requires clarification",
            )

            langgraph_conditional_edges_total.labels(
                edge_name="route_from_planner",
                decision="approval_gate",
            ).inc()

            langgraph_node_transitions_total.labels(
                from_node=NODE_PLANNER,
                to_node=NODE_SEMANTIC_VALIDATOR,
            ).inc()

            return "approval_gate"

    # === STEP 1: Route to response if no valid plan ===
    # This handles cases where:
    # 1. Planner couldn't generate steps (no applicable tools)
    # 2. Conversational query that slipped through routing
    # Going to approval_gate with no plan would cause incorrect "user rejected" message
    if step_count == 0:
        logger.info(
            "route_from_planner_no_plan_to_response",
            plan_id=plan_id,
            reason="Planner generated 0 steps, routing to conversational response",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_planner",
            decision="response",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_PLANNER,
            to_node=NODE_RESPONSE,
        ).inc()

        return "response"

    # Determine if the plan is multi-domain (true complexity)
    # Uses centralized helper for object/dict access
    domains = get_qi_attr(state, "domains", default=[])
    is_multi_domain = len(domains) > 1

    # FIX 2026-01-11: Check if this is a replanned iteration
    # Replanned plans MUST go through semantic validation to verify the replan
    # addresses the original issues. Without this, bad replans bypass validation.
    planner_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)

    # FIX 2026-01-11: Detect mutation intent mismatch
    # If original intent was mutation but plan has no mutation tool → bad replan
    is_mutation_intent = get_qi_attr(state, "is_mutation_intent", default=False)

    # Route to semantic_validator if:
    # 1. requires_hitl (mutations) - safety for destructive actions
    # 2. multi-domain - complexity requiring semantic validation
    # 3. FIX 2026-01-11: replanned plan (planner_iteration > 0) - must re-validate
    # 4. FIX 2026-01-11: mutation intent but no mutation in plan - likely incomplete
    requires_validation = False
    validation_reason = None

    if validation_result and validation_result.requires_hitl:
        requires_validation = True
        validation_reason = "requires_hitl"
    elif is_multi_domain:
        requires_validation = True
        validation_reason = "multi_domain"
    elif planner_iteration > 0:
        # FIX 2026-01-11: Replanned plans must be re-validated
        # This prevents bad replans from bypassing semantic validation
        requires_validation = True
        validation_reason = "replanned_iteration"
    elif is_mutation_intent and not (validation_result and validation_result.requires_hitl):
        # FIX 2026-01-11: Mutation intent detected but no mutation tool in plan
        # This indicates an incomplete plan that needs validation
        requires_validation = True
        validation_reason = "mutation_intent_no_hitl_tool"

    if requires_validation:
        logger.info(
            "route_from_planner_to_approval_gate",
            plan_id=plan_id,
            requires_hitl=validation_result.requires_hitl if validation_result else False,
            is_multi_domain=is_multi_domain,
            step_count=step_count,
            validation_reason=validation_reason,
            planner_iteration=planner_iteration,
            is_mutation_intent=is_mutation_intent,
        )

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_planner",
            decision="approval_gate",
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_PLANNER,
            to_node=NODE_APPROVAL_GATE,
        ).inc()

        return "approval_gate"

    # Single-domain plan without mutation → direct execution
    logger.info(
        "route_from_planner_to_task_orchestrator",
        plan_id=plan_id,
        requires_hitl=False,
        is_multi_domain=is_multi_domain,
        step_count=step_count,
        planner_iteration=planner_iteration,
        is_mutation_intent=is_mutation_intent,
    )

    # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
    langgraph_conditional_edges_total.labels(
        edge_name="route_from_planner",
        decision="task_orchestrator",
    ).inc()

    # Track node transition
    langgraph_node_transitions_total.labels(
        from_node=NODE_PLANNER,
        to_node=NODE_TASK_ORCHESTRATOR,
    ).inc()

    return "task_orchestrator"


def route_from_approval_gate(
    state: MessagesState,
) -> Literal["task_orchestrator", "response", "planner"]:
    """
    Route depuis approval_gate vers task_orchestrator, response ou planner.

    Si le plan a été approuvé (plan_approved = True),
    route vers task_orchestrator pour exécution.

    Si needs_replan = True (REPLAN demandé par l'utilisateur),
    route vers planner pour régénérer le plan avec les nouvelles instructions.

    Si le plan a été rejeté ou modifié avec erreur,
    route vers response pour expliquer le rejet.

    Args:
        state: État du graph avec plan_approved flag et needs_replan flag

    Returns:
        - "task_orchestrator" si approuvé
        - "planner" si REPLAN demandé
        - "response" sinon (rejet)
    """
    plan_approved = state.get(STATE_KEY_PLAN_APPROVED, False)
    needs_replan = state.get(STATE_KEY_NEEDS_REPLAN, False)
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)

    # DIAGNOSTIC: Log execution_plan type for HITL resumption debugging
    # If execution_plan is a dict instead of ExecutionPlan, checkpoint restore failed
    if execution_plan is not None:
        execution_plan_type = type(execution_plan).__name__
        if execution_plan_type == "dict":
            logger.error(
                "route_from_approval_gate_execution_plan_is_dict",
                plan_approved=plan_approved,
                execution_plan_type=execution_plan_type,
                execution_plan_keys=(
                    list(execution_plan.keys()) if isinstance(execution_plan, dict) else None
                ),
                msg="ExecutionPlan not restored from checkpoint - HITL resumption will fail",
            )
            # Attempt recovery: treat as None to route to response with error
            execution_plan = None

    plan_id = execution_plan.plan_id if execution_plan else None

    # Case 1: REPLAN requested - return to planner to regenerate
    if needs_replan:
        replan_instructions = state.get(STATE_KEY_REPLAN_INSTRUCTIONS, "")
        logger.info(
            "route_from_approval_gate_to_planner",
            plan_id=plan_id,
            needs_replan=True,
            has_instructions=bool(replan_instructions),
        )

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_approval_gate",
            decision="planner",
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_APPROVAL_GATE,
            to_node=NODE_PLANNER,
        ).inc()

        return "planner"

    # Case 2: Plan approved - execution
    if plan_approved:
        # LOT 6 FIX: Safety check - block execution of empty plans
        # An empty plan (0 steps) should NEVER be executed
        # This happens when max_iterations bypass kicks in with incomplete clarification
        step_count = len(execution_plan.steps) if execution_plan and execution_plan.steps else 0
        if step_count == 0:
            # DIAGNOSTIC: Log why execution_plan is empty/None for HITL debugging
            # Common causes:
            # 1. execution_plan is None - checkpoint not restored properly
            # 2. execution_plan.steps is empty - planner generated empty plan
            # 3. execution_plan is dict - Pydantic model not restored from JSON
            logger.warning(
                "route_from_approval_gate_empty_plan_blocked",
                plan_id=plan_id,
                step_count=0,
                execution_plan_is_none=execution_plan is None,
                execution_plan_type=type(execution_plan).__name__ if execution_plan else "NoneType",
                msg="Empty plan approved but execution blocked - routing to response. "
                "If execution_plan is None, checkpoint restore may have failed during HITL resumption.",
            )

            langgraph_conditional_edges_total.labels(
                edge_name="route_from_approval_gate",
                decision="response",
            ).inc()

            langgraph_node_transitions_total.labels(
                from_node=NODE_APPROVAL_GATE,
                to_node=NODE_RESPONSE,
            ).inc()

            return "response"

        logger.info(
            "route_from_approval_gate_to_task_orchestrator",
            plan_id=plan_id,
            approved=True,
            step_count=step_count,
        )

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_approval_gate",
            decision="task_orchestrator",
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_APPROVAL_GATE,
            to_node=NODE_TASK_ORCHESTRATOR,
        ).inc()

        return "task_orchestrator"

    # Case 3: Plan rejected - response
    logger.info(
        "route_from_approval_gate_to_response",
        plan_id=plan_id,
        approved=False,
    )

    # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
    langgraph_conditional_edges_total.labels(
        edge_name="route_from_approval_gate",
        decision="response",
    ).inc()

    # Track node transition
    langgraph_node_transitions_total.labels(
        from_node=NODE_APPROVAL_GATE,
        to_node=NODE_RESPONSE,
    ).inc()

    return "response"


def route_from_semantic_validator(
    state: MessagesState,
) -> Literal["approval_gate", "clarification", "planner"]:
    """
    Route depuis semantic_validator vers approval_gate, clarification ou planner.

    Phase 2 OPTIMPLAN - Semantic Validation Flow:
    - Si requires_clarification=True → clarification (HITL interrupt)
    - Si planner_iteration >= max_replans → approval_gate (max iterations atteintes)
    - Sinon → approval_gate (validation OK ou pas de clarification)

    Protection feedback loop:
    - Max iterations configurable via PLANNER_MAX_REPLANS (default: 2)
    - Au-delà, bypass clarification et passe à l'approbation

    Args:
        state: État du graph avec semantic_validation result

    Returns:
        - "clarification" si clarification requise (et < max_replans iterations)
        - "planner" si needs_replan=True (après clarification)
        - "approval_gate" si validation OK ou max iterations atteintes

    Notes:
        - needs_replan est set par clarification_node après réponse user
        - planner_iteration est incrémenté par clarification_node
        - Le cycle: planner → validator → clarification → (needs_replan) → planner
    """
    semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)
    planner_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)
    needs_replan = state.get(STATE_KEY_NEEDS_REPLAN, False)

    # Protection feedback loop: Use configurable max replans
    # Issue #60 Fix: Was hardcoded to 3, now uses planner_max_replans setting
    from src.core.config import get_settings

    settings = get_settings()
    max_iterations = settings.planner_max_replans

    # =========================================================================
    # BUG FIX 2025-12-07: Handle plan_approved flag for confirmation-only issues
    # =========================================================================
    # When user confirms a destructive operation (DANGEROUS_AMBIGUITY), clarification_node
    # sets plan_approved=True instead of needs_replan=True. This means the plan was
    # correct and user confirmed to proceed - skip re-validation and go to approval_gate.
    # Without this, semantic_validator would re-detect the same issue → infinite loop.
    # =========================================================================
    plan_approved = state.get(STATE_KEY_PLAN_APPROVED, False)
    if plan_approved:
        logger.info(
            "route_from_semantic_validator_plan_approved",
            plan_approved=True,
            planner_iteration=planner_iteration,
            msg="User confirmed plan via clarification, proceeding to approval_gate",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="approval_gate",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_APPROVAL_GATE,
        ).inc()

        return "approval_gate"

    # =========================================================================
    # Case 2: needs_replan=True - User responded to clarification (HIGHEST PRIORITY)
    # =========================================================================
    # BUG FIX 2026-01-14: Check needs_replan FIRST, before max_iterations
    # When user responds to clarification, clarification_node sets needs_replan=True.
    # We MUST route to planner to process the user's response, regardless of:
    # - max_iterations (user deserves to have their response processed)
    # - requires_clarification (stale from previous validation)
    # Without this fix: max_iterations bypass prevents processing user's last response
    # =========================================================================
    if needs_replan:
        logger.info(
            "route_from_semantic_validator_to_planner_needs_replan",
            planner_iteration=planner_iteration,
            needs_replan=True,
            msg="User responded to clarification, routing to planner to process response",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="planner",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_PLANNER,
        ).inc()

        return "planner"

    # =========================================================================
    # Case 3: Max iterations - bypass clarification/auto-replan
    # =========================================================================
    # Only checked AFTER needs_replan, because user's explicit response
    # should always be processed. This prevents auto-replan loops only.
    #
    # BUG FIX 2026-01-18: Use > instead of >= to allow max_replans iterations.
    # If max_replans=2, we want to allow 2 replans (iterations 1 and 2).
    # The counter is incremented AFTER validation fails, so:
    #   - iteration=1: first replan (1 > 2? No → replan allowed)
    #   - iteration=2: second replan (2 > 2? No → replan allowed)
    #   - iteration=3: third replan (3 > 2? Yes → BYPASS)
    # =========================================================================
    if planner_iteration > max_iterations:
        logger.warning(
            "route_from_semantic_validator_max_iterations_bypass",
            planner_iteration=planner_iteration,
            max_iterations=max_iterations,
            msg="Max iterations reached, routing to approval_gate",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="approval_gate",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_APPROVAL_GATE,
        ).inc()

        return "approval_gate"

    # =========================================================================
    # From here: planner_iteration < max_iterations AND needs_replan=False
    # =========================================================================

    # Case 4: No semantic validation result - fallback to approval
    if not semantic_validation:
        logger.warning(
            "route_from_semantic_validator_no_validation_result",
            msg="No semantic_validation in state, routing to approval_gate",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="approval_gate",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_APPROVAL_GATE,
        ).inc()

        return "approval_gate"

    # =========================================================================
    # Extract validation data once (DRY)
    # =========================================================================
    if hasattr(semantic_validation, "model_dump"):
        validation_dict = semantic_validation.model_dump()
    elif hasattr(semantic_validation, "__dataclass_fields__"):
        from dataclasses import asdict

        validation_dict = asdict(semantic_validation)
    elif isinstance(semantic_validation, dict):
        validation_dict = semantic_validation
    else:
        validation_dict = semantic_validation if hasattr(semantic_validation, "get") else {}

    requires_clarification = validation_dict.get("requires_clarification", False)
    is_valid = validation_dict.get("is_valid", True)

    # =========================================================================
    # Case 5: Clarification required (new problem detected by semantic_validator)
    # =========================================================================
    # Only reached if:
    # - needs_replan=False (user hasn't responded yet, checked in Cas 2)
    # - planner_iteration < max_iterations (checked in Cas 3)
    # This means semantic_validator detected a NEW problem requiring user input.
    # =========================================================================
    if requires_clarification:
        execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
        plan_id = execution_plan.plan_id if execution_plan else None
        logger.info(
            "route_from_semantic_validator_to_clarification",
            plan_id=plan_id,
            requires_clarification=True,
            planner_iteration=planner_iteration,
            question_count=len(validation_dict.get("clarification_questions", [])),
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="clarification",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_CLARIFICATION,
        ).inc()

        return "clarification"

    # =========================================================================
    # Case 6: Auto-replan - Issues found but Planner can self-correct
    # =========================================================================
    # SemanticValidator ↔ Planner dialogue without user interruption
    # Note: planner_iteration < max_iterations already guaranteed by Case 2
    # =========================================================================
    if not is_valid and not requires_clarification:
        execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
        plan_id = execution_plan.plan_id if execution_plan else None
        issues = validation_dict.get("issues", [])
        logger.info(
            "route_from_semantic_validator_auto_replan",
            plan_id=plan_id,
            is_valid=False,
            requires_clarification=False,
            planner_iteration=planner_iteration,
            issue_count=len(issues),
            msg="Semantic validator found fixable issues, returning to planner for auto-correction",
        )

        langgraph_conditional_edges_total.labels(
            edge_name="route_from_semantic_validator",
            decision="planner",
        ).inc()

        langgraph_node_transitions_total.labels(
            from_node=NODE_SEMANTIC_VALIDATOR,
            to_node=NODE_PLANNER,
        ).inc()

        return "planner"

    # =========================================================================
    # Case 7: Validation OK - proceed to approval
    # =========================================================================
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
    plan_id = execution_plan.plan_id if execution_plan else None
    logger.info(
        "route_from_semantic_validator_to_approval_gate",
        plan_id=plan_id,
        requires_clarification=False,
        is_valid=is_valid,
    )

    langgraph_conditional_edges_total.labels(
        edge_name="route_from_semantic_validator",
        decision="approval_gate",
    ).inc()

    langgraph_node_transitions_total.labels(
        from_node=NODE_SEMANTIC_VALIDATOR,
        to_node=NODE_APPROVAL_GATE,
    ).inc()

    return "approval_gate"
