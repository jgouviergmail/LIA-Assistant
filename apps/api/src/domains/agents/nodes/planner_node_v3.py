"""
Planner Node - Smart Planning with Filtered Catalogue.

Architecture v3 - Intelligence, Autonomy, Relevance.

DIFFERENCES with legacy HierarchicalPlannerService:
1. ONE LLM call (not 3 stages)
2. FILTERED catalogue by intent (not full)
3. Cross-domain handled by templates, not LLM

Token efficiency:
- Legacy: Stage1 (1600) + Stage2 (12000) + Stage3 (500) = 14100 tokens
- Current: Single call with filtered catalogue = ~1500 tokens
- Savings: 89%

PANIC MODE: If planning fails with filtered catalogue,
retry ONCE with expanded catalogue.

TEMPLATE ESCAPE HATCH: If multi-domain query doesn't match
any template, use generative planning (LLM).
Templates cover 80% (Pareto), LLM handles the rest.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    CLARIFICATION_RECIPIENT_FIELDS,
    TOOL_NAME_DELEGATE_SUB_AGENT,
)
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.analysis.query_intelligence_helpers import (
    get_query_intelligence_from_state,
)
from src.domains.agents.constants import (
    STATE_KEY_CLARIFICATION_FIELD,
    STATE_KEY_CLARIFICATION_RESPONSE,
    STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_MESSAGES,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_ROUTING_HISTORY,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.models import MessagesState
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_node_executions_total,
    planner_errors_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = get_logger(__name__)

# New state keys for v3
STATE_KEY_PLANNING_RESULT = "planning_result"


@trace_node("planner_v3")
@track_metrics(node_name="planner_v3")
async def planner_node_v3(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Planner node v3 - Smart planning with filtered catalogue.

    Flow:
    1. Get QueryIntelligence from state
    2. Call SmartPlannerService
    3. If fails -> PANIC MODE (retry with expanded catalogue)
    4. Return plan in state

    This uses filtered catalogues (96% token reduction)
    and cross-domain templates (zero extra LLM calls for 80% of cases).
    """
    from src.domains.agents.services.smart_planner_service import (
        get_smart_planner_service,
    )

    configurable = config.get("configurable", {})
    run_id = configurable.get(FIELD_RUN_ID, "unknown")

    # Get QueryIntelligence from state (uses centralized helper)
    # Priority: object version (_query_intelligence_obj) > dict reconstruction
    intelligence = get_query_intelligence_from_state(state)

    if not intelligence:
        logger.warning(
            "planner_v3_no_intelligence",
            run_id=run_id,
        )
        # Fall back to creating minimal intelligence
        from src.domains.agents.analysis.query_intelligence import (
            QueryIntelligence,
            UserGoal,
        )

        messages = state.get(STATE_KEY_MESSAGES, [])
        query = ""
        if messages:
            last = messages[-1]
            query = last.content if hasattr(last, "content") else str(last)

        routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])
        domains = []
        if routing_history:
            last_route = routing_history[-1]
            if hasattr(last_route, "domains"):
                domains = last_route.domains or []

        intelligence = QueryIntelligence(
            original_query=query,
            english_query=query,
            immediate_intent="search",
            immediate_confidence=0.5,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Default fallback",
            domains=domains,
            primary_domain=domains[0] if domains else "general",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=False,
            confidence=0.5,
            reasoning_trace=["Fallback - no intelligence in state"],
        )

    logger.info(
        "planner_v3_start",
        run_id=run_id,
        domains=intelligence.domains,
        intent=intelligence.immediate_intent,
        user_goal=intelligence.user_goal.value,
    )

    # Check if this is a replan iteration with previous validation feedback
    planner_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)
    validation_feedback = None

    # =========================================================================
    # BUG FIX 2026-01-14: Read clarification_response OUTSIDE planner_iteration check
    # =========================================================================
    # CRITICAL: clarification_response must be read INDEPENDENTLY of planner_iteration.
    # After clarification, planner_iteration is still 0 (only incremented by auto-replan).
    # Without this fix: clarification response is never read → plan ignores user's answer!
    # =========================================================================
    clarification_response = state.get(STATE_KEY_CLARIFICATION_RESPONSE)

    # If we have a clarification response, this IS a replan iteration even if counter=0
    # We increment planner_iteration to ensure route_from_planner sends us through
    # semantic_validator for proper validation of the new plan
    if clarification_response and planner_iteration == 0:
        planner_iteration = 1  # Treat as first replan iteration
        logger.info(
            "planner_v3_clarification_iteration_upgrade",
            run_id=run_id,
            clarification_field=state.get(STATE_KEY_CLARIFICATION_FIELD),
            msg="Upgraded planner_iteration to 1 due to clarification response",
        )

    if clarification_response:
        logger.info(
            "planner_v3_with_clarification",
            run_id=run_id,
            planner_iteration=planner_iteration,
            clarification_field=state.get(STATE_KEY_CLARIFICATION_FIELD),
            clarification_length=len(clarification_response),
            clarification_preview=clarification_response[:100] if clarification_response else "",
        )

    if planner_iteration > 0:
        semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)
        if semantic_validation:
            validation_feedback = _format_validation_feedback(semantic_validation)
            # Extract issue details for logging
            issues_summary = []
            if hasattr(semantic_validation, "issues"):
                for issue in semantic_validation.issues:
                    issue_type = (
                        issue.issue_type.value
                        if hasattr(issue.issue_type, "value")
                        else str(issue.issue_type)
                    )
                    issues_summary.append(
                        {
                            "type": issue_type,
                            "description": issue.description[:100] if issue.description else "",
                            "step_index": issue.step_index,
                            "suggested_fix": (
                                issue.suggested_fix[:50] if issue.suggested_fix else None
                            ),
                        }
                    )
            logger.info(
                "planner_v3_replan_with_feedback",
                run_id=run_id,
                planner_iteration=planner_iteration,
                issue_count=(
                    len(semantic_validation.issues) if hasattr(semantic_validation, "issues") else 0
                ),
                issues=issues_summary,
                feedback_preview=validation_feedback[:200] if validation_feedback else "",
            )

            # =================================================================
            # FOR_EACH DIRECTIVE INJECTION ON CARDINALITY_MISMATCH
            # =================================================================
            # When semantic validator detects a cardinality_mismatch issue,
            # the planner needs the FOR_EACH directive to know the exact syntax.
            # However, for_each_detected may be False in the original intelligence
            # because the user didn't use explicit "chaque/each" keywords.
            #
            # Fix: If we detect cardinality_mismatch, update intelligence to
            # set for_each_detected=True so the planner gets the directive.
            # =================================================================
            if hasattr(semantic_validation, "issues") and semantic_validation.issues:
                from dataclasses import replace as dataclass_replace

                has_cardinality_mismatch = any(
                    (
                        issue.issue_type.value
                        if hasattr(issue.issue_type, "value")
                        else str(issue.issue_type)
                    )
                    == "cardinality_mismatch"
                    for issue in semantic_validation.issues
                    if hasattr(issue, "issue_type")
                )

                if has_cardinality_mismatch and not intelligence.for_each_detected:
                    # Infer collection key from domains if not set
                    # Uses domain_taxonomy as single source of truth for result_key mapping
                    from src.domains.agents.registry.domain_taxonomy import get_result_key

                    collection_key = intelligence.for_each_collection_key
                    if not collection_key:
                        # For action domains (routes, weather), look for source domain
                        # in the full domains list to find what we're iterating over
                        source_domains = ["calendar", "event", "contact", "place"]
                        for domain in intelligence.domains:
                            # Try exact match first, then singular form
                            result_key = get_result_key(domain) or get_result_key(
                                domain.rstrip("s")
                            )
                            if result_key and domain.rstrip("s") in source_domains:
                                collection_key = result_key
                                break

                        # Fallback to primary domain mapping
                        if not collection_key and intelligence.primary_domain:
                            collection_key = (
                                get_result_key(intelligence.primary_domain)
                                or get_result_key(intelligence.primary_domain.rstrip("s"))
                                or "items"
                            )

                    intelligence = dataclass_replace(
                        intelligence,
                        for_each_detected=True,
                        for_each_collection_key=collection_key,
                    )

                    logger.info(
                        "planner_v3_for_each_activated_on_cardinality_mismatch",
                        run_id=run_id,
                        for_each_collection_key=collection_key,
                        msg="Activated FOR_EACH directive due to cardinality_mismatch",
                    )

    # Track if we should clear needs_replan flag (used when returning plan)
    should_clear_needs_replan = bool(clarification_response)

    # =========================================================================
    # EARLY INSUFFICIENT CONTENT DETECTION (Token Optimization)
    # =========================================================================
    # On first iteration only, check if user hasn't provided enough content
    # for a mutation operation. This saves ~5,000-10,000 tokens by avoiding
    # planner LLM calls when we know clarification is needed.
    #
    # Example: "send an email to marie" without subject/body
    # - Without early detection: 2 planner calls before clarification
    # - With early detection: 0 planner calls, immediate clarification
    #
    # GUARD: Skip when the QueryAnalyzer has semantically identified a skill.
    # Skill invocations (whether deterministic via SkillBypassStrategy or
    # model-driven via the LLM planner) must be allowed to reach the planner
    # pipeline so the skill's template or instructions can shape the plan.
    # =========================================================================
    if planner_iteration == 0 and not clarification_response:
        if _has_potential_skill_match(intelligence):
            logger.info(
                "planner_v3_early_detection_skipped_for_skill",
                run_id=run_id,
                msg="Potential skill match — letting planner pipeline decide",
            )
        else:
            from src.domains.agents.orchestration.semantic_validator import (
                detect_early_insufficient_content,
            )

            # Use english_enriched_query if available (post Semantic Pivot)
            english_query = getattr(intelligence, "english_enriched_query", None)
            if not english_query:
                english_query = getattr(intelligence, "english_query", None)
            if not english_query:
                english_query = intelligence.original_query

            user_language = state.get("user_language", settings.default_language)

            early_result = detect_early_insufficient_content(
                query_intelligence=intelligence,
                user_request=english_query,
                user_language=user_language,
            )

            if early_result and early_result.requires_clarification:
                logger.info(
                    "planner_v3_early_insufficient_content",
                    run_id=run_id,
                    requires_clarification=True,
                    issue_count=len(early_result.issues),
                    msg="Early detection saved planner LLM call(s)",
                )
                # Return early with semantic_validation set for clarification routing
                return {
                    STATE_KEY_EXECUTION_PLAN: None,
                    STATE_KEY_SEMANTIC_VALIDATION: early_result,
                }

    # Get SmartPlannerService
    planner_service = get_smart_planner_service()

    # Get clarification field if available (set by clarification_node)
    clarification_field = state.get(STATE_KEY_CLARIFICATION_FIELD)

    # DEBUG: Log values to trace resolution flow
    logger.debug(
        "planner_v3_clarification_debug",
        run_id=run_id,
        has_clarification_response=bool(clarification_response),
        clarification_response_preview=(
            clarification_response[:50] if clarification_response else None
        ),
        clarification_field=clarification_field,
        recipient_fields=list(CLARIFICATION_RECIPIENT_FIELDS),
        field_in_recipients=(
            clarification_field in CLARIFICATION_RECIPIENT_FIELDS if clarification_field else False
        ),
    )

    # =========================================================================
    # MEMORY REFERENCE RESOLUTION FOR CLARIFICATION RESPONSES
    # =========================================================================
    # When user provides a relational reference like "ma femme" for recipient,
    # we need to resolve it to an actual email/name using memory facts.
    # Without this, the planner would use "ma femme" literally → email validation fails.
    # =========================================================================
    if clarification_response and clarification_field in CLARIFICATION_RECIPIENT_FIELDS:
        resolved_clarification = await _resolve_clarification_reference(
            clarification_response=clarification_response,
            clarification_field=clarification_field,
            config=config,
            run_id=run_id,
        )
        if resolved_clarification != clarification_response:
            logger.info(
                "planner_v3_clarification_resolved",
                run_id=run_id,
                original=clarification_response,
                resolved=resolved_clarification,
                field=clarification_field,
            )
            clarification_response = resolved_clarification

    # Get existing execution plan for parameter preservation during multi-step clarification
    # When replanning after clarifying one field (e.g., body), we need to preserve
    # parameters that were already set in previous clarifications (e.g., subject="retard")
    existing_plan = state.get(STATE_KEY_EXECUTION_PLAN) if clarification_response else None

    # Get tool selection scores from router (for catalogue filtering)
    tool_selection_result = state.get("tool_selection_result")

    # F6: Exclude sub-agent tools from catalogue after user rejection
    exclude_tools: set[str] | None = None
    if state.get(STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS):
        exclude_tools = {TOOL_NAME_DELEGATE_SUB_AGENT}

    # =========================================================================
    # JOURNAL CONTEXT INJECTION (for planner reasoning)
    # =========================================================================
    journal_context = ""
    journal_planner_debug: dict | None = None
    user_journals_enabled = config.get("configurable", {}).get("user_journals_enabled", False)
    from src.core.config import get_settings as _get_settings

    _settings = _get_settings()
    if getattr(_settings, "journals_enabled", False) and user_journals_enabled:
        try:
            user_id_for_journal = configurable.get("langgraph_user_id")
            if user_id_for_journal and intelligence:
                from src.domains.journals.context_builder import build_journal_context
                from src.infrastructure.database.session import get_db_context

                planner_query = intelligence.original_query
                thread_id_for_journal = configurable.get("thread_id")

                # Use centralized embedding (cache by text hash → shared with response_node)
                from src.infrastructure.llm.user_message_embedding import (
                    get_or_compute_embedding,
                )

                planner_embedding = await get_or_compute_embedding(
                    message=planner_query,
                    user_id=user_id_for_journal,
                    session_id=thread_id_for_journal,
                )

                async with get_db_context() as journal_db:
                    journal_context_result, planner_journal_debug_data = (
                        await build_journal_context(
                            user_id=user_id_for_journal,
                            query=planner_query,
                            db=journal_db,
                            query_embedding=planner_embedding,
                            include_debug=True,
                            run_id=run_id,
                            session_id=thread_id_for_journal,
                        )
                    )
                    journal_context = journal_context_result or ""
                    journal_planner_debug = planner_journal_debug_data
        except Exception as e:
            logger.warning(
                "planner_journal_context_failed",
                run_id=run_id,
                error=str(e),
            )

    # Inject oauth_scopes into configurable so bypass strategies can filter
    # steps requiring scopes the user lacks (no interface change needed).
    if "oauth_scopes" not in configurable:
        configurable["oauth_scopes"] = state.get("oauth_scopes", [])

    # Plan with smart filtering
    planning_result = await planner_service.plan(
        intelligence=intelligence,
        config=config,
        validation_feedback=validation_feedback,
        clarification_response=clarification_response,
        clarification_field=clarification_field,
        existing_plan=existing_plan,
        tool_selection_result=tool_selection_result,
        exclude_tools=exclude_tools,
        journal_context=journal_context,
    )

    if planning_result.success and planning_result.plan:
        logger.info(
            "planner_v3_success",
            run_id=run_id,
            steps=len(planning_result.plan.steps),
            tokens_used=planning_result.tokens_used,
            tokens_saved=planning_result.tokens_saved,
            used_template=planning_result.used_template,
            used_panic_mode=planning_result.used_panic_mode,
        )

        agent_node_executions_total.labels(node_name="planner_v3", status="success").inc()

        # Validate plan to determine HITL requirements
        from src.domains.agents.orchestration.validator import (
            PlanValidator,
            ValidationContext,
        )
        from src.domains.agents.registry import get_global_registry

        validator = PlanValidator(get_global_registry())
        validation_context = ValidationContext(
            user_id=configurable.get("user_id", "unknown"),
            session_id=configurable.get("session_id", run_id),
            available_scopes=state.get("oauth_scopes", []),
            allow_hitl=True,  # Allow HITL by default
        )
        validation_result = validator.validate_execution_plan(
            planning_result.plan, validation_context
        )

        logger.info(
            "planner_v3_validation",
            run_id=run_id,
            is_valid=validation_result.is_valid,
            requires_hitl=validation_result.requires_hitl,
            errors_count=len(validation_result.errors),
        )

        result = {
            STATE_KEY_EXECUTION_PLAN: planning_result.plan,
            STATE_KEY_PLANNING_RESULT: planning_result,
            STATE_KEY_VALIDATION_RESULT: validation_result,
            "journal_planner_injection_debug": journal_planner_debug,
        }
        # BUG FIX 2026-01-14: Clear stale state after processing clarification
        # This prevents:
        # 1. needs_replan=True causing infinite loop in route_from_semantic_validator
        # 2. semantic_validation.requires_clarification=True causing route_from_planner
        #    to route to early_clarification path instead of normal flow
        # 3. clarification_response/field persisting to subsequent turns
        if should_clear_needs_replan:
            result[STATE_KEY_NEEDS_REPLAN] = False
            result[STATE_KEY_SEMANTIC_VALIDATION] = None  # Clear stale validation
            result[STATE_KEY_CLARIFICATION_RESPONSE] = None  # Clear used clarification
            result[STATE_KEY_CLARIFICATION_FIELD] = None  # Clear used field
            # BUG FIX 2026-01-14: Set planner_iteration so route_from_planner sees it
            # This ensures routing goes through semantic_validator after clarification
            result[STATE_KEY_PLANNER_ITERATION] = planner_iteration
        # F6: Clear replan flags after processing (scoped to single replan cycle)
        # Prevents infinite loop in route_from_semantic_validator (Case 2: needs_replan)
        if state.get(STATE_KEY_NEEDS_REPLAN):
            result[STATE_KEY_NEEDS_REPLAN] = False
        if state.get(STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS):
            result[STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS] = False
        return result
    else:
        logger.error(
            "planner_v3_failed",
            run_id=run_id,
            error=planning_result.error,
            used_panic_mode=planning_result.used_panic_mode,
            domain=intelligence.primary_domain,
            domains=intelligence.domains,
        )

        planner_errors_total.labels(
            error_type="planning_failed",
        ).inc()
        agent_node_executions_total.labels(node_name="planner_v3", status="error").inc()

        result = {
            STATE_KEY_EXECUTION_PLAN: None,
            STATE_KEY_PLANNING_RESULT: planning_result,
            STATE_KEY_VALIDATION_RESULT: None,  # No plan = no validation needed
            "journal_planner_injection_debug": journal_planner_debug,
        }
        # BUG FIX 2026-01-14: Clear stale state after processing clarification
        if should_clear_needs_replan:
            result[STATE_KEY_NEEDS_REPLAN] = False
            result[STATE_KEY_SEMANTIC_VALIDATION] = None  # Clear stale validation
            result[STATE_KEY_CLARIFICATION_RESPONSE] = None  # Clear used clarification
            result[STATE_KEY_CLARIFICATION_FIELD] = None  # Clear used field
            # BUG FIX 2026-01-14: Set planner_iteration so route_from_planner sees it
            result[STATE_KEY_PLANNER_ITERATION] = planner_iteration
        # F6: Clear replan flags after processing (scoped to single replan cycle)
        if state.get(STATE_KEY_NEEDS_REPLAN):
            result[STATE_KEY_NEEDS_REPLAN] = False
        if state.get(STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS):
            result[STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS] = False
        return result


async def _resolve_clarification_reference(
    clarification_response: str,
    clarification_field: str,
    config: RunnableConfig,
    run_id: str,
) -> str:
    """
    Resolve memory-based references in clarification responses.

    When user provides "ma femme" (FR) or "my wife" (EN) as recipient,
    resolve it to actual email using:
    1. Memory facts (relational references → name)
    2. Contacts lookup (name → email)

    Resolution Strategy:
    1. Skip if already a valid email (contains @domain)
    2. Try memory resolution (handles multilingual via LLM)
    3. Lookup email in contacts
    4. Return original if no resolution (tool validation will provide clear error)

    Args:
        clarification_response: User's response (e.g., "ma femme", "my wife", "jean@example.com")
        clarification_field: Field being clarified (from CLARIFICATION_RECIPIENT_FIELDS)
        config: RunnableConfig for LLM calls and token tracking
        run_id: Run ID for logging

    Returns:
        Resolved email address, or original response if no resolution found
    """
    logger.info(
        "clarification_resolution_started",
        run_id=run_id,
        clarification_response=clarification_response,
        clarification_field=clarification_field,
    )

    # Skip if already looks like a valid email
    if "@" in clarification_response and "." in clarification_response.split("@")[-1]:
        logger.debug(
            "clarification_resolution_skipped_valid_email",
            run_id=run_id,
            response=clarification_response,
        )
        return clarification_response

    # Try memory + contacts resolution (LLM handles multilingual pattern detection)
    # Pattern: Same as QueryAnalyzerService._get_memory_facts() + _resolve_memory_references()
    try:
        from src.domains.agents.middleware.memory_injection import get_memory_facts_for_query
        from src.domains.agents.services.memory_reference_resolution_service import (
            get_memory_reference_resolution_service,
        )

        configurable = config.get("configurable", {})
        # Use langgraph_user_id (str) like QueryAnalyzerService
        user_id = configurable.get("langgraph_user_id")

        if not user_id:
            logger.debug(
                "clarification_resolution_no_user_id",
                run_id=run_id,
            )
            return clarification_response

        # Get memory facts for this user (embeds locally, no store needed)
        memory_facts = await get_memory_facts_for_query(
            user_id=user_id,
            query=clarification_response,
        )

        if not memory_facts:
            logger.debug(
                "clarification_resolution_no_memory_facts",
                run_id=run_id,
            )
            return clarification_response

        # Convert list to string for resolution service
        memory_facts_str = "\n".join(f"- {fact}" for fact in memory_facts)

        # Resolve using memory reference resolution service
        # Extract user_language from config for multilingual resolution
        configurable = config.get("configurable", {}) if config else {}
        user_language = configurable.get("user_language", settings.default_language)

        resolution_service = get_memory_reference_resolution_service()
        result = await resolution_service.resolve_pre_planner(
            query=clarification_response,
            memory_facts=memory_facts_str,
            user_language=user_language,
            config=config,
        )

        if result.has_resolutions():
            # Memory resolved "my wife" → "Jane Smith" (name)
            # send_email_tool will resolve name → email via contacts
            resolved_name = result.enriched_query
            logger.info(
                "clarification_resolution_memory_success",
                run_id=run_id,
                original=clarification_response,
                resolved=resolved_name,
                mappings=result.mappings,
            )
            return resolved_name

        # No memory resolution - return original (might be a name or email)
        # send_email_tool will handle name → email resolution if needed
        return clarification_response

    except Exception as e:
        logger.warning(
            "clarification_resolution_error",
            run_id=run_id,
            error=str(e),
            response=clarification_response,
        )
        return clarification_response


def get_planner_v3_edge(
    state: MessagesState,
) -> str:
    """
    Edge function for planner v3.

    Routes to validator if plan exists, response if not.
    """
    plan = state.get(STATE_KEY_EXECUTION_PLAN)
    if plan and hasattr(plan, "steps") and plan.steps:
        return "validator"

    # No plan - go to response with error message
    return "response"


def _format_validation_feedback(semantic_validation) -> str:
    """
    Format SemanticValidationResult issues for planner prompt injection.

    Converts semantic issues into actionable guidance that helps
    the planner avoid repeating the same mistakes.

    Args:
        semantic_validation: SemanticValidationResult dataclass or dict

    Returns:
        Formatted feedback string for the planner prompt
    """
    if not semantic_validation:
        return ""

    # Handle both dataclass and dict access patterns
    if hasattr(semantic_validation, "issues"):
        issues = semantic_validation.issues
    elif isinstance(semantic_validation, dict):
        issues = semantic_validation.get("issues", [])
    else:
        return ""

    if not issues:
        return ""

    lines = ["PREVIOUS PLAN VALIDATION FAILED. Issues detected:"]

    for i, issue in enumerate(issues, 1):
        # Handle both Pydantic model and dict access
        if hasattr(issue, "issue_type"):
            issue_type = (
                issue.issue_type.value
                if hasattr(issue.issue_type, "value")
                else str(issue.issue_type)
            )
            description = issue.description
            step_index = issue.step_index
            suggested_fix = issue.suggested_fix
        else:
            issue_type = issue.get("issue_type", "unknown")
            description = issue.get("description", "")
            step_index = issue.get("step_index")
            suggested_fix = issue.get("suggested_fix")

        step_info = f" (step {step_index})" if step_index is not None else ""
        lines.append(f"{i}. [{issue_type}]{step_info} - {description}")

        if suggested_fix:
            lines.append(f"   FIX: {suggested_fix}")

    lines.append("")
    lines.append("CRITICAL: You MUST address ALL issues above in your new plan.")

    return "\n".join(lines)


def _has_potential_skill_match(intelligence: Any) -> bool:
    """Return True when the QueryAnalyzer has semantically identified a skill.

    Used to gate early insufficient content detection: when a skill has been
    identified (whether deterministic or not), we skip the early short-circuit
    and let the full planner pipeline decide — SkillBypassStrategy for
    deterministic skills, LLM planner (using the skill's description and
    instructions) for the rest.

    No cache lookup is performed here: presence of ``detected_skill_name`` in
    the intelligence is a sufficient signal that the query maps to a skill.
    Downstream code enforces the proper user-scoped skill resolution.

    Args:
        intelligence: QueryIntelligence produced by the QueryAnalyzer, which
            sets ``detected_skill_name`` when a skill description matches the
            user's request.

    Returns:
        True when ``intelligence.detected_skill_name`` is set.
    """
    skill_name = getattr(intelligence, "detected_skill_name", None)
    if not skill_name:
        return False

    logger.info(
        "potential_skill_match_detected",
        skill_name=skill_name,
        msg="Skipping early insufficient content detection",
    )
    return True


# Alias for backward compatibility
planner_node = planner_node_v3
