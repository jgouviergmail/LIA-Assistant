"""
Semantic Validator Node - LangGraph node for plan semantic validation.

This module provides a LangGraph node that validates execution plans against
user intent, detecting subtle semantic issues like:
- Cardinality mismatches ("pour chaque" → single operation)
- Missing dependencies
- Implicit assumptions
- Scope overflow/underflow

Architecture:
    Planner → SemanticValidatorNode → validation result in state
    → route_from_semantic_validator decides: approval_gate OR clarification

Pattern: LangGraph v1.0 async node
    - Node updates state with semantic_validation result
    - Conditional edge uses result to route to next node
    - No interrupt() in this node (validation only)
    - ClarificationNode handles interrupt if needed

Usage in Graph:
    graph.add_node("semantic_validator", semantic_validator_node)
    # NOTE: Semantic validation is always enabled (no conditional edge needed)

References:
    - OPTIMPLAN/PLAN.md: Section 4 - Phase 2
    - semantic_validator.py: PlanSemanticValidator logic
    - clarification_node.py: Handles clarification interrupts

Created: 2025-11-25 (Phase 2.4 OPTIMPLAN)
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.i18n import DEFAULT_LANGUAGE
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.domains.agents.orchestration.semantic_validator import (
    PlanSemanticValidator,
    plan_contains_mutation,
)
from src.domains.agents.utils.shape_agnostic import read_field
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: How many distinct questions a single clarification may carry. More than that
#: reads as a wall of text rather than a question.
_MAX_CLARIFICATION_QUESTIONS = 3


def _questions_for_issues(issues: list[Any], user_language: str) -> list[str]:
    """Turn semantic issues into something the user can actually answer.

    Prefers the issue's own ``description`` when it is user-facing: the LLM path
    honours the "in user's language" contract and says something SPECIFIC ("La
    date de début est incorrecte"), which beats any generic question. Falls back
    to the localized question for the issue type when the description is
    technical (the deterministic rules, ``user_facing=False``) or empty —
    showing one delivered "for_each pattern issue detected" to a French account
    (prod 2026-08-02).

    Deduplicated on the RESULTING TEXT, not on the issue type: distinct types can
    legitimately share one question — ``cardinality_mismatch`` and
    ``for_each_missing_cardinality`` are two diagnoses of the same thing to ask,
    and asking it twice reads as a bug. Deduplicating on the text also keeps two
    genuinely different LLM descriptions of one type, which each carry their own
    information. Capped, so a clarification stays a question rather than a wall
    of text.

    Args:
        issues: The verdict's issues, as models or mappings.
        user_language: The account's language; variants are normalized by the
            i18n accessor.

    Returns:
        Up to ``_MAX_CLARIFICATION_QUESTIONS`` entries, in first-seen order.
        Empty when there is no issue to ask about.
    """
    from src.core.i18n_hitl import HitlMessages

    questions: list[str] = []
    seen: set[str] = set()
    for issue in issues or []:
        issue_type = read_field(issue, "issue_type")
        if issue_type is None:
            continue
        # `SemanticIssueType` is a (str, Enum): `.value` is the table key.
        key = str(getattr(issue_type, "value", issue_type))

        description = str(read_field(issue, "description", "")).strip()
        if description and read_field(issue, "user_facing", True):
            question = description
        else:
            question = HitlMessages.get_semantic_issue_question(key, user_language)

        if question in seen:
            continue
        seen.add(question)
        questions.append(question)

        if len(questions) >= _MAX_CLARIFICATION_QUESTIONS:
            break

    return questions


async def semantic_validator_node(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    LangGraph node for semantic validation of execution plans.

    Validates that the generated plan semantically matches the user's original
    request by detecting:
    - Cardinality mismatches (single op vs "pour chaque")
    - Missing dependencies between steps
    - Implicit assumptions about data
    - Scope overflow/underflow

    Gold Grade Features:
        - Short-circuit for trivial plans (≤1 step)
        - Always enabled (critical for plan quality)
        - Timeout protection with optimistic fallback
        - Fast LLM model (GPT-4.1-mini) for sub-2s validation

    Args:
        state: LangGraph state dict containing:
            - execution_plan: ExecutionPlan from planner
            - messages: Conversation history (for user request)
            - user_language: Language code (fr, en, es)
        config: Optional RunnableConfig for LangGraph

    Returns:
        Dict with state updates:
            - semantic_validation: SemanticValidationResult with:
                - is_valid: True if plan matches intent
                - issues: List of detected semantic issues
                - requires_clarification: True if user input needed
                - clarification_questions: Questions to ask user

    Raises:
        None: All errors are caught and logged. Failed validation defaults
              to "valid" (optimistic fallback) to prevent blocking execution.

    Example State Flow:
        >>> # Before validation
        >>> state = {
        ...     "execution_plan": ExecutionPlan(...),
        ...     "messages": [HumanMessage(content="Envoie email à tous mes contacts")],
        ...     "user_language": "fr",
        ... }
        >>>
        >>> # After validation
        >>> new_state = await semantic_validator_node(state, config)
        >>> new_state["semantic_validation"].requires_clarification  # True if ambiguous
        >>> new_state["semantic_validation"].clarification_questions  # ["Voulez-vous..."]

    Performance:
        - Short-circuit (≤1 step): ~1ms
        - LLM validation (2-5 steps): 800ms-2s (P95 < 2s)
        - Timeout fallback: 1s (optimistic pass)

    Notes:
        - This node does NOT trigger interrupts - it only validates
        - If requires_clarification=True, route_from_semantic_validator routes to clarification_node
        - ClarificationNode then triggers the actual interrupt
        - If feature flag disabled, returns instant "valid" result
    """
    # =========================================================================
    # BUG FIX 2025-12-07: Skip validation if plan_approved=True
    # =========================================================================
    # When user confirms a destructive operation (DANGEROUS_AMBIGUITY) via clarification,
    # clarification_node sets plan_approved=True. We should NOT re-validate the plan
    # because it would re-detect the same issue → infinite loop (recursion limit).
    # Instead, return a valid result and let routing proceed to execution.
    # =========================================================================
    plan_approved = state.get(STATE_KEY_PLAN_APPROVED, False)
    if plan_approved:
        logger.info(
            "semantic_validator_node_plan_approved_skip",
            plan_approved=True,
            msg="User confirmed plan via clarification, skipping re-validation",
        )
        # Return valid result to allow execution
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticValidationResult,
        )

        return {
            STATE_KEY_SEMANTIC_VALIDATION: SemanticValidationResult(
                is_valid=True,
                issues=[],
                confidence=1.0,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=0.0,
                used_fallback=False,
            )
        }

    # =========================================================================
    # BUG FIX 2026-01-14: Only preserve early detection clarification if NO plan exists
    # =========================================================================
    # When detect_early_insufficient_content() triggers BEFORE the planner runs,
    # it sets requires_clarification=True with NO execution_plan. We preserve this.
    #
    # However, after clarification and replanning, execution_plan WILL exist.
    # In that case, we MUST validate the new plan instead of preserving the stale
    # early detection result. Without this fix, the stale requires_clarification=True
    # causes semantic_validator to preserve it, and route_from_semantic_validator
    # sees needs_replan=True (from clarification_node) → routes to planner → loop!
    #
    # Fix: Only preserve if requires_clarification=True AND no execution_plan exists.
    # =========================================================================
    existing_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)

    if existing_validation and not execution_plan:
        # Handle both dict and object access patterns
        if isinstance(existing_validation, dict):
            requires_clarification = existing_validation.get("requires_clarification", False)
        else:
            requires_clarification = getattr(existing_validation, "requires_clarification", False)

        if requires_clarification:
            logger.info(
                "semantic_validator_node_preserving_clarification",
                source="planner",
                has_execution_plan=False,
                msg="Preserving requires_clarification=True from early detection (no plan exists)",
            )
            # Return existing validation unchanged - early detection triggered, no plan yet
            return {STATE_KEY_SEMANTIC_VALIDATION: existing_validation}

    # NOTE: Semantic validation is always enabled

    # Extract required data from state
    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
    # DEFAULT_LANGUAGE, not a "fr" literal: the fallback has to follow
    # `settings.default_language`, or a deployment configured in another
    # language would still get its clarification questions in French.
    user_language = state.get("user_language") or DEFAULT_LANGUAGE

    # Safety check: execution_plan must exist
    if not execution_plan:
        logger.error(
            "semantic_validator_node_no_execution_plan",
            has_execution_plan=False,
        )
        # Return valid fallback (fail-open)
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticValidationResult,
        )

        return {
            STATE_KEY_SEMANTIC_VALIDATION: SemanticValidationResult(
                is_valid=True,
                issues=[],
                confidence=0.5,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=0.0,
                used_fallback=True,
            )
        }

    # Extract user request - prefer english_query from QueryIntelligence (v3 architecture)
    # This ensures consistency with Semantic Pivot: all internal processing uses English
    # Uses centralized helper for object/dict access
    english_query = get_qi_attr(state, "english_query", default=None)

    # The user's ORIGINAL wording, always extracted: with the pivot active it
    # rides along as the AUTHORITY for content/names/language (runtime defect
    # 2026-07-30: validating against the English pivot alone flagged French
    # content args, folded recipient names and a phantom reply id).
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        original_query = (
            coerce_content_to_text(last_message.content)
            if hasattr(last_message, "content")
            else str(last_message)
        )
    else:
        logger.warning(
            "semantic_validator_node_no_messages",
            has_messages=False,
        )
        original_query = ""

    original_request: str | None = None
    if english_query:
        user_request = english_query
        original_request = original_query or None
        logger.debug(
            "semantic_validator_using_english_query",
            source="query_intelligence",
            english_query_preview=user_request[:100] if user_request else "",
            has_original=bool(original_request),
        )
    else:
        user_request = original_query
        logger.debug(
            "semantic_validator_using_original_message",
            source="messages_fallback",
            reason="query_intelligence not available or english_query empty",
        )

    # The request preview is the USER'S MESSAGE — "message bodies" is on the
    # short list of things that never belong at INFO. `add_pii_filter` catches
    # e-mails but not everything a person types (a national-format phone number
    # goes through untouched, measured), so the level is the real guard here.
    # Counters and ids stay, the content moves down.
    logger.info(
        "semantic_validator_node_validating",
        plan_id=execution_plan.plan_id if hasattr(execution_plan, "plan_id") else None,
        step_count=len(execution_plan.steps) if hasattr(execution_plan, "steps") else 0,
        user_language=user_language,
        request_length=len(user_request),
    )
    logger.debug(
        "semantic_validator_node_validating_request",
        user_request_preview=user_request[:100],
    )

    # Initialize validator and run validation
    validator = PlanSemanticValidator()

    # v3.1: Get query_intelligence for LLM-detected flags (mutation, cardinality)
    query_intelligence = state.get("query_intelligence")

    try:
        validation_result = await validator.validate(
            plan=execution_plan,
            user_request=user_request,
            user_language=user_language,
            config=config,
            query_intelligence=query_intelligence,
            original_request=original_request,
        )

        logger.info(
            "semantic_validator_node_complete",
            is_valid=validation_result.is_valid,
            requires_clarification=validation_result.requires_clarification,
            issue_count=len(validation_result.issues),
            confidence=validation_result.confidence,
            duration_seconds=validation_result.validation_duration_seconds,
            used_fallback=validation_result.used_fallback,
        )

        # =================================================================
        # PLAN PATTERN LEARNING (fire-and-forget)
        # =================================================================
        # Record success/failure for pattern learning to improve future plans
        # Uses fire-and-forget (async task) so it doesn't block the flow
        # =================================================================
        from src.domains.agents.analysis.query_intelligence_helpers import (
            get_query_intelligence_from_state,
        )
        from src.domains.agents.services.plan_pattern_learner import (
            record_plan_failure,
            record_plan_success,
        )

        # Get QueryIntelligence object (not dict) for pattern learning
        qi_object = get_query_intelligence_from_state(state)

        if qi_object:
            if validation_result.is_valid and not validation_result.requires_clarification:
                # Plan validated successfully - record as success
                record_plan_success(execution_plan, qi_object)
                logger.info(
                    "pattern_learning_recorded_success_semantic_validator",
                    is_valid=validation_result.is_valid,
                    requires_clarification=validation_result.requires_clarification,
                )
            elif not validation_result.is_valid:
                # Plan rejected - record as failure for learning
                record_plan_failure(execution_plan, qi_object)
                logger.info(
                    "pattern_learning_recorded_failure_semantic_validator",
                    is_valid=validation_result.is_valid,
                )
            else:
                # requires_clarification without invalid -> not recorded (ambiguous)
                logger.debug(
                    "pattern_learning_skipped_ambiguous",
                    is_valid=validation_result.is_valid,
                    requires_clarification=validation_result.requires_clarification,
                )
        else:
            logger.debug(
                "pattern_learning_skipped_no_qi_semantic_validator",
                reason="qi_object is None",
            )

        # Build state updates
        state_updates = {STATE_KEY_SEMANTIC_VALIDATION: validation_result}

        # If issues found and needs auto-replan, increment iteration counter
        # This prevents infinite loops (max: PLANNER_MAX_REPLANS setting)
        if not validation_result.is_valid and not validation_result.requires_clarification:
            from src.core.config import settings

            current_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)
            # This increment would produce the value at which the router bypasses
            # (planner_iteration > planner_max_replans): auto-replans are exhausted.
            exhausting = current_iteration + 1 > settings.planner_max_replans
            execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)

            if exhausting and plan_contains_mutation(execution_plan):
                # SAFETY NET (mutations only): the max-iterations bypass would
                # execute this still-INVALID mutation plan (silently wrong — prod
                # 2026-07-17: a calendar event created on the wrong day after the
                # replanner failed to converge). Hand it to a HITL clarification
                # instead: the routing then takes Case 5 (clarification, since the
                # iteration is NOT bumped past the bypass threshold) and
                # ClarificationInteraction then STREAMS these questions as they
                # are — it does not synthesize anything from the issues (its LLM
                # branch is unbuilt and only yields a generic fallback), so what
                # is written just below is literally what the user reads.
                # Read-only plans keep the bypass — a wrong read is harmless and
                # asking would only annoy.
                validation_result.requires_clarification = True
                # Ask something the user can answer, in their language. An issue
                # description is shown ONLY when its producer declared it
                # showable (`user_facing`): the deterministic rules set it False
                # because theirs are English technical literals, and recycling
                # them shipped "for_each pattern issue detected" plus a
                # fabricated address to a French account (prod 2026-08-02, 4
                # occurrences in 30 days). See `_questions_for_issues` for the
                # cap and for why the de-duplication is on the TEXT.
                if not validation_result.clarification_questions:
                    validation_result.clarification_questions = _questions_for_issues(
                        validation_result.issues, user_language
                    )
                # planner_iteration deliberately NOT incremented: a clarification
                # is not an auto-replan (2026-01-14) and the un-bumped value is
                # what keeps the router on the clarification branch.
                logger.warning(
                    "semantic_validator_node_mutation_exhausted_to_clarification",
                    planner_iteration=current_iteration,
                    issue_count=len(validation_result.issues),
                    msg="Invalid mutation plan exhausted auto-replans; asking the user "
                    "instead of executing a wrong mutation",
                )
            else:
                state_updates[STATE_KEY_PLANNER_ITERATION] = current_iteration + 1
                logger.info(
                    "semantic_validator_node_auto_replan_triggered",
                    planner_iteration=current_iteration + 1,
                    issue_count=len(validation_result.issues),
                    msg="Fixable issues found, will route back to planner for auto-correction",
                )

        return state_updates

    except Exception as e:
        # Unexpected error - log and return valid fallback
        logger.error(
            "semantic_validator_node_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

        from src.domains.agents.orchestration.semantic_validator import (
            SemanticValidationResult,
        )

        return {
            STATE_KEY_SEMANTIC_VALIDATION: SemanticValidationResult(
                is_valid=True,
                issues=[],
                confidence=0.5,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=0.0,
                used_fallback=True,
            )
        }
