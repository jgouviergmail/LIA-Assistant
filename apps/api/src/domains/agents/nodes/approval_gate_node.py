"""
Approval Gate Node (Phase 8 - HITL Plan-Level)

This node presents ExecutionPlans to users for approval BEFORE execution.
It replaces the problematic tool-level HITL that interrupted execution mid-stream.

Architecture:
    1. Check if plan requires approval (validation_result.requires_hitl)
    2. If not, pass through to execution
    3. If yes, present complete plan summary to user
    4. Call interrupt() to pause and wait for user decision
    5. Process decision: APPROVE → execute, REJECT → response, EDIT → re-validate
    6. Return appropriate state updates for routing

Flow:
    Planner → Approval Gate → interrupt() → User Decision → Resume
                           ↓ approved              ↓ rejected
                     TaskOrchestrator           Response

References:
    - HITL_PLAN_LEVEL_ARCHITECTURE.md: Complete architecture documentation
    - approval_schemas.py: PlanApprovalRequest/Decision structures
    - plan_editor.py: Apply user modifications to plans
"""

import time
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.domains.agents.constants import (
    STATE_KEY_APPROVAL_EVALUATION,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_REPLAN_INSTRUCTIONS,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_SESSION_ID,
    STATE_KEY_USER_ID,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.approval_schemas import (
    PlanApprovalRequest,
    PlanSummary,
    StepSummary,
)
from src.domains.agents.orchestration.plan_editor import (
    PlanEditor,
    PlanModificationError,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationContext,
)
from src.domains.agents.registry import get_global_registry
from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator
from src.domains.agents.utils.state_tracking import track_state_updates
from src.infrastructure.observability.callbacks import TokenTrackingCallback
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    hitl_plan_approval_latency,
    hitl_plan_approval_question_duration,
    hitl_plan_approval_question_fallback,
    hitl_plan_approval_requests,
    hitl_plan_decisions,
    hitl_plan_modifications,
)
from src.infrastructure.observability.metrics_business import (
    agent_tool_approval_rate,
    hitl_feature_usage_total,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _extract_agent_types_from_plan(plan: ExecutionPlan) -> list[str]:
    """
    Extract unique agent_types from an ExecutionPlan.

    Converts agent_name (e.g., "contacts_agent") → agent_type (e.g., "contacts")
    using the "_agent" suffix removal pattern.

    Args:
        plan: ExecutionPlan containing steps with agent_name

    Returns:
        List of unique agent_types (no duplicates)

    Example:
        >>> plan = ExecutionPlan(steps=[
        ...     ExecutionStep(agent_name="contacts_agent", ...),
        ...     ExecutionStep(agent_name="emails_agent", ...),
        ...     ExecutionStep(agent_name="contacts_agent", ...),  # duplicate
        ... ])
        >>> _extract_agent_types_from_plan(plan)
        ["contacts", "emails"]
    """
    agent_types = set()

    for step in plan.steps:
        agent_name = step.agent_name

        # Skip steps without agent (e.g., CONDITIONAL steps)
        # ExecutionStep.agent_name is Optional[str] and can be None for non-TOOL steps
        if not agent_name:
            continue

        # Pattern: "contacts_agent" → "contacts"
        if agent_name.endswith("_agent"):
            agent_type = agent_name[:-6]  # Remove "_agent" suffix
        else:
            agent_type = agent_name  # Fallback: use full name
        agent_types.add(agent_type)

    return list(agent_types)


def _build_plan_summary(plan: ExecutionPlan, validation_result: Any) -> PlanSummary:
    """
    Build a plan summary for user presentation.

    Args:
        plan: Complete execution plan
        validation_result: Validation result with costs and flags

    Returns:
        PlanSummary for UI display
    """
    registry = get_global_registry()
    steps = []
    hitl_steps_count = 0

    for step in plan.steps:
        # Get manifest for metadata (check global registry + user MCP context)
        manifest = None
        if step.tool_name:
            try:
                manifest = registry.get_tool_manifest(step.tool_name)
            except Exception:
                # Fallback: MCP tools with hallucinated suffix (evolution F2.1/F2.5)
                from src.core.context import (
                    strip_hallucinated_mcp_suffix,
                    user_mcp_tools_ctx,
                )

                manifest = None

                # 1. Admin MCP: strip suffix and retry central registry
                stripped = strip_hallucinated_mcp_suffix(step.tool_name)
                if stripped:
                    try:
                        manifest = registry.get_tool_manifest(stripped)
                    except Exception:
                        pass

                # 2. User MCP: ContextVar with fuzzy resolve
                if manifest is None:
                    user_ctx = user_mcp_tools_ctx.get()
                    if user_ctx:
                        manifest = user_ctx.resolve_tool_manifest(step.tool_name)

                if manifest is None:
                    logger.warning(
                        "manifest_not_found_for_step",
                        tool_name=step.tool_name,
                    )

        # Determine if step requires HITL
        step_hitl_required = (
            manifest and manifest.permissions.hitl_required
        ) or step.approvals_required

        if step_hitl_required:
            hitl_steps_count += 1

        step_summary = StepSummary(
            step_id=step.step_id,
            tool_name=step.tool_name or "N/A",
            description=step.description or f"Execute {step.tool_name}",
            parameters=step.parameters,
            estimated_cost_usd=(manifest.cost.est_cost_usd if manifest else 0.0),
            hitl_required=step_hitl_required,
            data_classification=(manifest.permissions.data_classification if manifest else None),
            required_scopes=(manifest.permissions.required_scopes if manifest else []),
        )
        steps.append(step_summary)

    return PlanSummary(
        plan_id=plan.plan_id,
        total_steps=len(plan.steps),
        total_cost_usd=validation_result.total_cost_usd,
        hitl_steps_count=hitl_steps_count,
        steps=steps,
        generated_at=datetime.now(UTC),
    )


async def _build_approval_request(
    plan_summary: PlanSummary,
    validation_result: Any,
    approval_evaluation: Any = None,
    user_language: str = "fr",
    user_timezone: str = "Europe/Paris",
    config: RunnableConfig | None = None,
    skip_question_generation: bool = True,
) -> PlanApprovalRequest:
    """
    Build a complete approval request.

    Phase 1 HITL Streaming (OPTIMPLAN):
    When skip_question_generation=True (default), the question is NOT generated here.
    Instead, StreamingService generates it lazily via LLM streaming for better TTFT.

    Args:
        plan_summary: Plan summary
        validation_result: Validation result
        approval_evaluation: Strategy evaluation result (optional)
        user_language: User language for the question (default: "fr")
        user_timezone: User's IANA timezone for datetime context (default: "Europe/Paris")
        config: LangGraph RunnableConfig to extract TokenTrackingCallback (optional)
        skip_question_generation: If True, skip LLM question generation here.
            The question will be generated via streaming in StreamingService.
            Default: True (Phase 1 HITL Streaming)

    Returns:
        PlanApprovalRequest to send to the user
    """
    # Extract reasons and strategies
    reasons = []
    strategies_triggered = []

    if approval_evaluation:
        reasons = approval_evaluation.reasons
        strategies_triggered = approval_evaluation.strategies_triggered
    elif validation_result.requires_hitl:
        # Fallback if no approval_evaluation
        reasons = ["Plan contains tools requiring HITL approval"]
        strategies_triggered = ["ManifestBasedStrategy"]

    # Phase 1 HITL Streaming: Skip question generation here if enabled
    # The question will be generated via LLM streaming in StreamingService
    # This achieves TTFT < 500ms instead of 2-4s blocking here
    if skip_question_generation:
        logger.info(
            "approval_gate_skip_question_generation",
            plan_id=plan_summary.plan_id,
            msg="Question will be generated via streaming in StreamingService",
        )
        user_message = None  # Will be generated in StreamingService
    else:
        # Legacy behavior: Generate question here (blocking)
        # Extract TokenTrackingCallback from config for accurate token tracking
        tracker = None
        if config:
            callbacks = config.get("callbacks", [])
            # Ensure callbacks is iterable (could be None or other type)
            if callbacks and isinstance(callbacks, list):
                for callback in callbacks:
                    if isinstance(callback, TokenTrackingCallback):
                        tracker = callback
                        break

        # Generate contextual approval question using LLM
        start_time = time.time()
        try:
            generator = HitlQuestionGenerator()
            user_message = await generator.generate_plan_approval_question(
                plan_summary=plan_summary,
                approval_reasons=reasons,
                user_language=user_language,
                user_timezone=user_timezone,
                tracker=tracker,  # ✅ Pass tracker for token tracking
            )

            generation_duration = time.time() - start_time
            hitl_plan_approval_question_duration.observe(generation_duration)

            logger.info(
                "approval_gate_llm_question_generated",
                plan_id=plan_summary.plan_id,
                question_length=len(user_message),
                generation_duration_seconds=generation_duration,
                user_language=user_language,
            )
        except Exception as e:
            # Track fallback usage
            error_type = type(e).__name__
            hitl_plan_approval_question_fallback.labels(error_type=error_type).inc()

            # Fallback to improved static message (no cost display) if LLM fails
            logger.warning(
                "approval_gate_llm_question_failed_using_fallback",
                plan_id=plan_summary.plan_id,
                error=str(e),
                error_type=error_type,
            )

            # Improved fallback: Shows what actions will be performed, no cost
            # Uses centralized i18n for all 6 supported languages (fr, en, es, de, it, zh-CN)
            from src.domains.agents.api.error_messages import SSEErrorMessages

            user_message = SSEErrorMessages.plan_approval_fallback(
                step_count=plan_summary.total_steps,
                language=user_language,
            )

    return PlanApprovalRequest(
        plan_summary=plan_summary,
        approval_reasons=reasons,
        strategies_triggered=strategies_triggered,
        user_message=user_message,
    )


def _process_approval_decision(
    decision_data: dict[str, Any],
    plan: ExecutionPlan,
    context: ValidationContext,
) -> tuple[bool, ExecutionPlan | None, str, str | None]:
    """
    Traite la décision d'approbation de l'utilisateur.

    Phase 3.2 Enhancement:
    - Tracks framework metrics (hitl_plan_decisions) - existing
    - Tracks business metrics (hitl_feature_usage_total, agent_tool_approval_rate) - NEW

    Issue #63 Enhancement: REPLAN support
    - REPLAN now returns replan_instructions for planner regeneration
    - Enables action type changes via HITL (e.g., search → details)

    Args:
        decision_data: Données de décision depuis interrupt resume
        plan: Plan original
        context: Contexte de validation

    Returns:
        Tuple (approved, modified_plan, rejection_reason, replan_instructions)
            approved: True si plan approuvé
            modified_plan: Plan modifié si EDIT, None sinon
            rejection_reason: Raison du rejet si REJECT
            replan_instructions: Instructions pour re-planification si REPLAN, None sinon
    """
    decision = decision_data.get("decision", "REJECT")

    # Extract agent types from plan for business metrics
    agent_types = _extract_agent_types_from_plan(plan)

    if decision == "APPROVE":
        logger.info("plan_approved_by_user", plan_id=plan.plan_id)

        # Framework metric (existing)
        hitl_plan_decisions.labels(decision="APPROVE").inc()

        # Business metrics (Phase 3.2 - Step 2.3)
        # Track HITL feature usage
        for agent_type in agent_types:
            hitl_feature_usage_total.labels(
                interaction_type="approval", agent_type=agent_type
            ).inc()

        # Track approval rate (1.0 = all tools approved)
        for agent_type in agent_types:
            agent_tool_approval_rate.labels(agent_type=agent_type).observe(1.0)

        return True, None, "", None

    elif decision == "REJECT":
        rejection_reason = decision_data.get("rejection_reason", "User rejected plan")
        logger.info(
            "plan_rejected_by_user",
            plan_id=plan.plan_id,
            reason=rejection_reason,
        )

        # Framework metric (existing)
        hitl_plan_decisions.labels(decision="REJECT").inc()

        # Business metrics (Phase 3.2 - Step 2.3)
        # Track HITL feature usage
        for agent_type in agent_types:
            hitl_feature_usage_total.labels(interaction_type="reject", agent_type=agent_type).inc()

        # Track approval rate (0.0 = all tools rejected)
        for agent_type in agent_types:
            agent_tool_approval_rate.labels(agent_type=agent_type).observe(0.0)

        return False, None, rejection_reason, None

    elif decision == "EDIT":
        modifications = decision_data.get("modifications", [])

        if not modifications:
            logger.warning(
                "edit_decision_without_modifications",
                plan_id=plan.plan_id,
            )
            return False, None, "EDIT decision requires modifications", None

        try:
            # Apply modifications
            editor = PlanEditor()
            from src.domains.agents.orchestration.approval_schemas import (
                PlanModification,
            )

            modification_objects = [PlanModification(**mod) for mod in modifications]
            modified_plan = editor.apply_modifications(plan, modification_objects)

            # Re-validate modified plan
            validator = PlanValidator(get_global_registry())
            validation_result = validator.validate_execution_plan(modified_plan, context)

            if not validation_result.is_valid:
                error_msg = f"Modified plan validation failed: {validation_result.errors}"
                logger.error(
                    "modified_plan_validation_failed",
                    plan_id=plan.plan_id,
                    errors=validation_result.errors,
                )
                return False, None, error_msg, None

            # Track modifications
            for mod in modification_objects:
                hitl_plan_modifications.labels(modification_type=mod.modification_type).inc()

            logger.info(
                "plan_edited_and_validated",
                plan_id=plan.plan_id,
                modification_count=len(modifications),
            )

            # Framework metric (existing)
            hitl_plan_decisions.labels(decision="EDIT").inc()

            # Business metrics (Phase 3.2 - Step 2.3)
            # Track HITL feature usage
            for agent_type in agent_types:
                hitl_feature_usage_total.labels(
                    interaction_type="edit", agent_type=agent_type
                ).inc()

            # Track approval rate (1.0 = plan continues after edit)
            for agent_type in agent_types:
                agent_tool_approval_rate.labels(agent_type=agent_type).observe(1.0)

            return True, modified_plan, "", None

        except PlanModificationError as e:
            error_msg = f"Failed to apply modifications: {str(e)}"
            logger.error(
                "plan_modification_failed",
                plan_id=plan.plan_id,
                error=str(e),
            )
            return False, None, error_msg, None

    elif decision == "REPLAN":
        # Issue #63: REPLAN now implemented - regenerate plan with new instructions
        replan_instructions = decision_data.get("replan_instructions", "")

        # Extract user's reformulated request from edited_params if available
        # This happens when classifier detects action type change (e.g., search → details)
        edited_params = decision_data.get("edited_params", {})
        if not replan_instructions and edited_params:
            # Build instructions from edited_params context
            # This captures the user's intent for the new action type
            if "new_action" in edited_params:
                replan_instructions = f"L'utilisateur veut: {edited_params['new_action']}"
            elif "reformulated_intent" in edited_params:
                replan_instructions = edited_params["reformulated_intent"]

        logger.info(
            "replan_requested",
            plan_id=plan.plan_id,
            has_instructions=bool(replan_instructions),
            instructions_preview=replan_instructions[:100] if replan_instructions else None,
        )

        # Framework metric (existing)
        hitl_plan_decisions.labels(decision="REPLAN").inc()

        # Business metrics (Phase 3.2 - Step 2.3)
        # Track HITL feature usage
        for agent_type in agent_types:
            hitl_feature_usage_total.labels(interaction_type="replan", agent_type=agent_type).inc()

        # Track approval rate (0.5 = plan modified significantly via replan)
        for agent_type in agent_types:
            agent_tool_approval_rate.labels(agent_type=agent_type).observe(0.5)

        # Return with replan_instructions (4th element)
        # approved=False (not executing current plan)
        # rejection_reason="" (not a rejection)
        # replan_instructions=user's new instructions
        return False, None, "", replan_instructions

    else:
        logger.warning(
            "unknown_approval_decision",
            plan_id=plan.plan_id,
            decision=decision,
        )
        return False, None, f"Unknown decision type: {decision}", None


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
    Approval Gate Node - Plan-Level HITL.

    Présente le plan complet à l'utilisateur pour approbation AVANT exécution.
    Utilise interrupt() pour pauser et attendre la décision.

    Métriques trackées automatiquement via @track_metrics:
    - agent_node_executions_total{node_name="approval_gate", status="success/error"}
    - agent_node_duration_seconds{node_name="approval_gate"}

    Métriques custom trackées dans la fonction:
    - hitl_plan_approval_requests_total
    - hitl_plan_decisions_total
    - hitl_plan_approval_question_duration_seconds

    Si plan approuvé: continue vers task_orchestrator
    Si plan rejeté: route vers response avec explication

    Args:
        state: État du graph avec execution_plan et validation_result
        config: Configuration LangGraph

    Returns:
        Dict avec plan_approved flag et éventuellement modified plan
    """
    start_time = time.time()

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
    approval_evaluation = state.get(STATE_KEY_APPROVAL_EVALUATION)
    semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)

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
    if not validation_result.requires_hitl:
        logger.info(
            "approval_gate_passthrough",
            plan_id=execution_plan.plan_id,
            msg="Plan does not require approval, passing through",
        )
        result_passthrough: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: True}
        track_state_updates(state, result_passthrough, "approval_gate", execution_plan.plan_id)
        return result_passthrough

    # Build plan summary
    plan_summary = _build_plan_summary(execution_plan, validation_result)

    # Extract user preferences from state
    user_language = state.get("user_language", "fr")
    user_timezone = state.get("user_timezone", "Europe/Paris")
    personality_instruction = state.get("personality_instruction")

    # Build approval request with LLM-generated question
    # Pass config to enable token tracking for plan approval question generation
    approval_request = await _build_approval_request(
        plan_summary, validation_result, approval_evaluation, user_language, user_timezone, config
    )

    # Track metrics
    strategies = approval_request.strategies_triggered
    for strategy in strategies:
        hitl_plan_approval_requests.labels(strategy=strategy).inc()

    logger.info(
        "approval_gate_requesting_approval",
        plan_id=execution_plan.plan_id,
        total_steps=plan_summary.total_steps,
        total_cost_usd=plan_summary.total_cost_usd,
        hitl_steps=plan_summary.hitl_steps_count,
        strategies_triggered=strategies,
    )

    # Interrupt and wait for user decision
    # LangGraph will save checkpoint and wait for resume
    # Format compatible with existing HITL infrastructure (action_requests pattern)
    # Use mode='json' to serialize datetime objects to ISO strings
    #
    # Phase 1 HITL Streaming (OPTIMPLAN):
    # - generate_question_streaming: True tells StreamingService to generate question via LLM streaming
    # - user_language: Passed for streaming question generation
    # - user_timezone: Passed for datetime context in prompts
    # - user_message: None when skip_question_generation=True (will be streamed in StreamingService)
    #
    # Semantic Validation Fallback Warning:
    # If semantic validation used fallback (timeout or error), include warning for user
    semantic_fallback_warning = None
    if semantic_validation and getattr(semantic_validation, "used_fallback", False):
        fallback_reason = getattr(semantic_validation, "fallback_reason", "unknown")
        semantic_fallback_warning = (
            f"⚠️ La validation du plan n'a pas pu être effectuée ({fallback_reason}). "
            "Veuillez vérifier attentivement le plan avant de l'approuver."
        )
        logger.warning(
            "approval_gate_semantic_validation_fallback",
            plan_id=execution_plan.plan_id,
            fallback_reason=fallback_reason,
            confidence=getattr(semantic_validation, "confidence", None),
        )

    interrupt_payload = {
        "action_requests": [
            {
                "type": "plan_approval",
                "plan_summary": approval_request.plan_summary.model_dump(mode="json"),
                "approval_reasons": approval_request.approval_reasons,
                "strategies_triggered": approval_request.strategies_triggered,
                "user_message": approval_request.user_message,
                # Personality instruction for HITL question generation
                "personality_instruction": personality_instruction,
                # Semantic validation fallback warning for UI display
                "semantic_fallback_warning": semantic_fallback_warning,
            }
        ],
        # Include full approval_request for backward compatibility
        "approval_request": approval_request.model_dump(mode="json"),
        # Phase 1 HITL Streaming: Flags for StreamingService
        "generate_question_streaming": approval_request.user_message is None,
        "user_language": user_language,
        "user_timezone": user_timezone,
        "personality_instruction": personality_instruction,
        # Semantic validation fallback warning (top-level for easy access)
        "semantic_fallback_warning": semantic_fallback_warning,
    }
    decision_data = interrupt(interrupt_payload)

    # After resume: process decision
    elapsed_time = time.time() - start_time
    hitl_plan_approval_latency.observe(elapsed_time)

    logger.info(
        "approval_gate_decision_received",
        plan_id=execution_plan.plan_id,
        decision=decision_data.get("decision") if decision_data else None,
        latency_seconds=elapsed_time,
        # Debug: Full decision data for EDIT troubleshooting
        has_modifications="modifications" in decision_data if decision_data else False,
        modifications_count=len(decision_data.get("modifications", [])) if decision_data else 0,
        modifications_preview=decision_data.get("modifications", [])[:2] if decision_data else None,
    )

    # If no decision data, treat as rejection (safety)
    if not decision_data:
        logger.warning(
            "approval_gate_no_decision_data",
            plan_id=execution_plan.plan_id,
        )
        result_no_decision: dict[str, Any] = {
            STATE_KEY_PLAN_APPROVED: False,
            STATE_KEY_PLAN_REJECTION_REASON: "No decision received from user",
        }
        track_state_updates(state, result_no_decision, "approval_gate", execution_plan.plan_id)
        return result_no_decision

    # Process decision
    # Need validation context for re-validation if EDIT
    # Issue #61 Fix: Use correct state key "oauth_scopes" (not "available_scopes")
    context = ValidationContext(
        user_id=state.get(STATE_KEY_USER_ID, "unknown"),
        session_id=state.get(STATE_KEY_SESSION_ID),
        available_scopes=state.get("oauth_scopes", []),  # FIXED: was "available_scopes"
        user_roles=state.get("user_roles", []),
        allow_hitl=True,  # Already in HITL flow
    )

    approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
        decision_data, execution_plan, context
    )

    # Build return state
    # NOTE: result is dict[str, Any] to allow mixed types (bool, str | None, ExecutionPlan)
    result: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: approved}

    # Issue #63: Handle REPLAN case - set needs_replan=True to route to planner
    if replan_instructions is not None:
        # REPLAN requested - route to planner for new plan generation
        result[STATE_KEY_NEEDS_REPLAN] = True
        result[STATE_KEY_REPLAN_INSTRUCTIONS] = replan_instructions
        # Clear rejection reason (this is not a rejection, it's a replan request)
        result[STATE_KEY_PLAN_REJECTION_REASON] = None
        # Clear execution plan to force fresh generation
        result[STATE_KEY_EXECUTION_PLAN] = None

        # Update HumanMessage with reformulated intent for planner context
        # The planner will see the user's new intent instead of original query
        if replan_instructions:
            from langchain_core.messages import HumanMessage

            result["messages"] = [HumanMessage(content=replan_instructions)]

        logger.info(
            "approval_gate_replan_requested",
            plan_id=execution_plan.plan_id,
            has_instructions=bool(replan_instructions),
            instructions_preview=replan_instructions[:50] if replan_instructions else None,
        )

    elif approved:
        # CRITICAL: Clear rejection reason from previous turn to prevent contamination
        # LangGraph state keys persist across turns unless explicitly cleared
        result[STATE_KEY_PLAN_REJECTION_REASON] = None
        # Clear needs_replan from any previous replan attempt
        result[STATE_KEY_NEEDS_REPLAN] = False

        # If plan was modified, update execution_plan in state
        if modified_plan:
            result[STATE_KEY_EXECUTION_PLAN] = modified_plan
            logger.info(
                "approval_gate_plan_modified",
                original_plan_id=execution_plan.plan_id,
                modified_plan_id=modified_plan.plan_id,
            )
    else:
        # Plan rejected - set state field (router_node clears this each turn)
        result[STATE_KEY_PLAN_REJECTION_REASON] = rejection_reason
        # Clear needs_replan
        result[STATE_KEY_NEEDS_REPLAN] = False

        logger.info(
            "approval_gate_plan_rejected",
            plan_id=execution_plan.plan_id,
            reason=rejection_reason,
        )

    # PHASE 2.5 - LangGraph Observability: Track state updates
    track_state_updates(state, result, "approval_gate", execution_plan.plan_id)

    return result
