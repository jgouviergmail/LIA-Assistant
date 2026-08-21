"""
Plan Semantic Validator - LLM-based validation of plan coherence.

This module validates that execution plans semantically match user intent,
detecting subtle issues like:
- Cardinality mismatches ("pour chaque" → single operation)
- Missing dependencies (step B needs step A result but no depends_on)
- Implicit assumptions (assuming data exists without verification)
- Scope overflows/underflows (doing too much/too little)

Architecture:
    - Uses a distinct LLM from planner (avoids self-validation bias)
    - Structured output via LangChain v1.0 patterns
    - Short-circuits for trivial plans (≤1 step)
    - Feature flag controlled (SEMANTIC_VALIDATION_ENABLED)
    - Timeout protection (optimistic validation with 1s limit)

Design Goals:
    - Catch plan issues BEFORE user approval (better UX)
    - Enable clarification flow for ambiguous requests
    - Maintain TTFT < 500ms via optional async validation
    - Production-ready error handling and fallback

References:
    - OPTIMPLAN/PLAN.md: Section 4 - Phase 2
    - LangChain v1.0: with_structured_output()
    - Issue #56: Architecture Planning Agentique

Created: 2025-11-25
"""

import asyncio
import re
import time
from contextlib import suppress
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.domains.agents.prompts import load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import StructuredOutputError, get_structured_output
from src.infrastructure.observability.logging import get_logger

from .for_each_rules import validate_for_each_patterns as validate_for_each_patterns

# Pure plan predicates extracted to plan_predicates.py (file-size ratchet):
# they answer "what does this plan do?" with no LLM and no I/O. Re-exported
# (``as`` form: explicit re-export under mypy strict) for historical callers.
from .plan_predicates import CROSS_DOMAIN_CAPABLE_TOOLS as CROSS_DOMAIN_CAPABLE_TOOLS
from .plan_predicates import MUTATION_TOOL_PATTERNS as MUTATION_TOOL_PATTERNS
from .plan_predicates import (
    detect_placeholder_contacts,
    plan_covers_domain,
    plan_writes_without_write_intent,
    tool_is_mutation,
)
from .plan_predicates import plan_contains_mutation as plan_contains_mutation
from .plan_schemas import ExecutionPlan

# Validation domain models extracted to validation_models.py (file-size
# ratchet — pure data contracts). Re-exported here (``as`` form: explicit
# re-export under mypy strict) so historical import sites keep working.
from .validation_models import CriticalityLevel as CriticalityLevel
from .validation_models import SemanticIssue as SemanticIssue
from .validation_models import SemanticIssueType as SemanticIssueType
from .validation_models import SemanticValidationOutput as SemanticValidationOutput
from .validation_models import SemanticValidationResult as SemanticValidationResult

logger = get_logger(__name__)

# ============================================================================
# Smart Validation Trigger Logic (v3.1 - LLM-based)
# ============================================================================
# v3.1 ARCHITECTURE CHANGE:
# - Mutation intent and cardinality risk are now detected by QueryAnalyzer LLM
# - CROSS_DOMAIN_PATTERNS removed (LLM detects secondary domains directly)
# - CARDINALITY_KEYWORDS removed (LLM sets has_cardinality_risk flag)
# - MUTATION_TOOL_PATTERNS kept only for tool name validation (internal data)
# ============================================================================


def _programmatic_rejection(
    issue_type: SemanticIssueType,
    description: str,
    suggested_fix: str,
    criticality: CriticalityLevel,
    started_at: float,
) -> SemanticValidationResult:
    """Build the verdict of a DETERMINISTIC rule (no LLM was consulted).

    The four pre-LLM rules reject the same way — one issue, full confidence, no
    clarification — so the shape lives here instead of being retyped at each
    site, where a divergence would be invisible.

    Args:
        issue_type: Which of the deadly sins the plan committed.
        description: What was detected, for the trace and the replan prompt.
        suggested_fix: The correction instruction handed back to the planner.
        criticality: How much the issue costs if executed as-is.
        started_at: ``time.time()`` at validation entry, for the duration.

    Returns:
        An invalid result carrying exactly one issue, routed to auto-replan.
    """
    return SemanticValidationResult(
        is_valid=False,
        issues=[
            SemanticIssue(
                issue_type=issue_type,
                description=description,
                suggested_fix=suggested_fix,
                severity="high",
                # These descriptions are English technical literals written for
                # the trace and the replan prompt — never for the user. Saying
                # so here is what keeps them out of a clarification question.
                user_facing=False,
            )
        ],
        confidence=1.0,  # Programmatic detection = 100% confident
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=time.time() - started_at,
        criticality=criticality,
    )


def should_trigger_semantic_validation(
    plan: ExecutionPlan,
    user_request: str,
    planner_confidence: float = 1.0,
    query_intelligence: Any | None = None,
) -> tuple[bool, str]:
    """
    Decide if semantic validation is worth the token cost.

    v3.1 ARCHITECTURE: Uses LLM-detected flags from QueryIntelligence instead of
    hardcoded patterns. This is more reliable as the LLM understands context.

    Decision matrix:
    - LLM detected mutation but plan has no mutation tool: VALIDATE (planner bug)
    - Multi-domain expected but single step: VALIDATE (planner bug)
    - Single step (no cross-domain): SKIP (trivially safe)
    - Multi-domain in plan: VALIDATE (coordination to verify)
    - LLM detected cardinality risk: VALIDATE (bulk operations are risky)
    - LLM detected mutation intent: VALIDATE (mutations need verification)
    - Batch reference + read-only: SKIP (safe pattern like search→details)
    - Low planner confidence: VALIDATE (uncertainty needs validation)

    Args:
        plan: ExecutionPlan to evaluate
        user_request: Original user message (for fallback only)
        planner_confidence: Confidence score from planner (0.0-1.0)
        query_intelligence: QueryIntelligence with LLM-detected flags (v3.1)

    Returns:
        (should_validate, reason): Tuple of boolean and reason string

    Example:
        >>> should, reason = should_trigger_semantic_validation(
        ...     plan, "recherche les contacts", query_intelligence=qi
        ... )
        >>> if should:
        ...     result = await validator.validate(plan, user_request)
    """
    # v3.1: Get LLM-detected flags from QueryIntelligence
    # Handle both dict (serialized) and object formats
    is_mutation_intent = False
    has_cardinality_risk = False
    expected_domains: list[str] = []
    primary_domain = ""

    if query_intelligence is not None:
        if isinstance(query_intelligence, dict):
            # Dict format (LangGraph serialization)
            is_mutation_intent = query_intelligence.get("is_mutation_intent", False)
            has_cardinality_risk = query_intelligence.get("has_cardinality_risk", False)
            expected_domains = query_intelligence.get("domains", [])
            primary_domain = query_intelligence.get("primary_domain", "") or ""
        else:
            # Object format (QueryIntelligence dataclass)
            is_mutation_intent = getattr(query_intelligence, "is_mutation_intent", False)
            has_cardinality_risk = getattr(query_intelligence, "has_cardinality_risk", False)
            expected_domains = getattr(query_intelligence, "domains", [])
            primary_domain = getattr(query_intelligence, "primary_domain", "") or ""

    # A single-step plan that touches NONE of the primary domain is not a
    # consolidation — it is a loss. Prod 2026-07-23: "weather for my two
    # appointments on July 25" was detected as primary_domain=weather, the
    # planner emitted a lone get_events_tool step, and the response node,
    # holding the question but no weather data, invented temperatures. The
    # rule below distinguishes the two cases the read-only exemption conflates:
    # consolidating several domains into one call still calls a PRIMARY-domain
    # tool; dropping the domain does not. Deterministic (registry lookup, no
    # LLM) and routed to silent auto-replan, not to a user clarification —
    # bounded by PLANNER_MAX_REPLANS.
    if primary_domain and len(plan.steps) == 1 and not plan_covers_domain(plan, primary_domain):
        return True, f"primary_domain_uncovered:{primary_domain}"

    # Check multi-domain mismatch (before single-step short-circuit)
    # If LLM detected 2+ domains but plan has only 1 step → possibly incomplete plan
    # BUT: Only force validation for MUTATION intents or cardinality risks.
    # For read-only queries (route, search, weather, info), the planner often correctly
    # consolidates multiple detected domains into a single tool call.
    # Forcing validation on read-only queries causes spurious clarification loops.
    if len(expected_domains) >= 2 and len(plan.steps) == 1:
        if is_mutation_intent or has_cardinality_risk:
            return True, f"multi_domain_expected_but_single_step:{expected_domains}"

    # CRITICAL: Detect intent-plan mismatch for single-step plans
    # If LLM detected mutation intent but plan has NO mutation tool → incomplete plan
    if is_mutation_intent and len(plan.steps) == 1:
        single_tool_name = plan.steps[0].tool_name or ""
        if not tool_is_mutation(single_tool_name):
            return True, f"mutation_intent_but_no_mutation_tool:{single_tool_name}"

    # Single-step MUTATIONS are validated: the only step writes real data, and a
    # planner that drops conversational context invents parameters silently
    # (observed in prod 2026-07-17: a breakfast agreed for Saturday 10:00 was
    # planned as a default next-hour slot on Friday — the skip below let it
    # through). Read-only single steps stay trivial: a wrong read is harmless
    # and spurious clarification loops on reads are worse than the miss.
    if len(plan.steps) <= 1:
        if plan.steps and tool_is_mutation(plan.steps[0].tool_name or ""):
            return True, "single_step_mutation"
        return False, "single_step_trivial"

    # =========================================================================
    # OPTIMIZATION 2026-01: Skip validation for well-formed cross-domain plans
    # =========================================================================
    has_step_references = False
    mutation_at_end = False

    for i, step in enumerate(plan.steps):
        params_str = str(step.parameters) if step.parameters else ""
        if "$steps.step_" in params_str:
            has_step_references = True

        # Check if last step is a mutation
        if i == len(plan.steps) - 1:
            tool_name = step.tool_name or ""
            mutation_at_end = tool_is_mutation(tool_name)

    if len(plan.steps) >= 2 and has_step_references and mutation_at_end:
        # Well-formed cross-domain mutation plan → skip validation
        return False, "well_formed_cross_domain_mutation"

    # 1. Multi-domain in plan: coordination needs verification
    plan_domains = set()
    for step in plan.steps:
        if step.agent_name:
            domain = step.agent_name.removesuffix("_agent")
            plan_domains.add(domain)
    if len(plan_domains) > 1:
        return True, f"multi_domain:{','.join(sorted(plan_domains))}"

    # 2. Any mutation tool in plan (risky operation)
    plan_has_mutation = any(tool_is_mutation(step.tool_name or "") for step in plan.steps)
    if plan_has_mutation:
        return True, "mutation_detected"

    # 3. LLM-detected cardinality risk (v3.1 - replaces hardcoded keywords)
    if has_cardinality_risk:
        return True, "llm_cardinality_risk"

    # 4. LLM-detected mutation intent (even if plan looks safe)
    if is_mutation_intent:
        return True, "llm_mutation_intent"

    # 5. Low planner confidence
    if planner_confidence < 0.8:
        return True, f"low_planner_confidence:{planner_confidence:.2f}"

    # 6. Batch reference analysis
    # If batch reference ([*]) exists but NO mutation → safe pattern (search→details)
    has_batch_reference = False
    for step in plan.steps:
        params_str = str(step.parameters) if step.parameters else ""
        if "$steps" in params_str and "[*]" in params_str:
            has_batch_reference = True
            break

    if has_batch_reference and not plan_has_mutation:
        # Safe pattern: batch read-only operation (like search → get_details)
        return False, "batch_read_only_safe"

    # Default: validate for safety
    return True, "default_validate"


# ============================================================================
# $steps Reference Validation (Ghost Dependency Detection)
# ============================================================================
# Pre-LLM detection of incorrect $steps references in plan parameters.
# The planner may generate references like $steps.step_2.events when step_2
# is actually a weather tool (result_key=weathers), not an events tool.
#
# This validation:
# 1. Builds a mapping step_id → expected_result_key based on tool names
# 2. Parses parameters to find $steps.step_X.domain_key references
# 3. Verifies that domain_key matches the result_key of step_X's tool
# 4. Returns REJECT status with correction feedback if mismatch detected
# ============================================================================

# Pattern to match $steps.step_X.domain_key references
_STEPS_REFERENCE_PATTERN = re.compile(
    r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)"
)


def _get_expected_result_key_for_tool(tool_name: str) -> str | None:
    """
    Get the expected result_key for a tool based on its name.

    Delegates to domain_taxonomy.get_result_key_for_tool() which is
    THE source of truth for tool → result_key mapping.

    Examples:
        get_weather_tool → "weathers"
        get_events_tool → "events"
        get_contacts_tool → "contacts"
        send_email_tool → "emails"
    """
    from src.domains.agents.registry.domain_taxonomy import get_result_key_for_tool

    return get_result_key_for_tool(tool_name)


def validate_steps_references(plan: ExecutionPlan) -> tuple[bool, str | None]:
    """
    Validate that $steps references in plan parameters use correct result_keys.

    Detects "ghost dependency" errors where the planner generates references
    to result_keys that don't match the tool of the referenced step.

    Example error:
        step_1: get_contacts_tool  (result_key: contacts)
        step_2: get_weather_tool   (result_key: weathers)
        step_3: get_events_tool    (result_key: events)
        step_4: send_email_tool with content_instruction="$steps.step_2.events"
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                    ERROR: step_2 produces "weathers", not "events"

    Args:
        plan: ExecutionPlan to validate

    Returns:
        (is_valid, error_feedback): Tuple of:
            - is_valid: True if all references are valid
            - error_feedback: Correction instruction for planner if invalid, None if valid
    """
    # Build mapping of step_id → expected_result_key
    step_result_keys: dict[str, str] = {}
    for step in plan.steps:
        result_key = _get_expected_result_key_for_tool(step.tool_name or "")
        if result_key:
            step_result_keys[step.step_id] = result_key

    # Find and validate all $steps references in parameters
    errors: list[str] = []

    for step in plan.steps:
        if not step.parameters:
            continue

        # Recursively search parameters for $steps references
        params_str = str(step.parameters)

        for match in _STEPS_REFERENCE_PATTERN.finditer(params_str):
            ref_step_id = match.group(1)  # e.g., "step_2"
            ref_domain_key = match.group(2)  # e.g., "events"

            # The regex captures ANY `$steps.X.Y`, but Y is a result_key only
            # some of the time — it is just as often a plain output FIELD
            # ("count", "success"), which the catalogue documents as a
            # legitimate reference (the unified read tools list "count" among
            # their own reference_examples). Ghost-dependency detection compares
            # DOMAIN keys, so a field access must be skipped: flagging it
            # rejected a valid plan and forced a wasted replan.
            from src.domains.agents.utils.type_domain_mapping import (
                get_domain_from_result_key,
            )

            if get_domain_from_result_key(ref_domain_key) is None:
                continue

            # Check if referenced step exists
            if ref_step_id not in step_result_keys:
                # Step doesn't exist or we couldn't determine its result_key
                # This might be valid if it's a special reference, skip
                continue

            expected_key = step_result_keys[ref_step_id]

            # Check if the domain_key matches the expected result_key
            if ref_domain_key != expected_key:
                # Find the correct step_id for this domain_key
                correct_step_id = None
                for sid, rkey in step_result_keys.items():
                    if rkey == ref_domain_key:
                        correct_step_id = sid
                        break

                if correct_step_id:
                    errors.append(
                        f"Reference '$steps.{ref_step_id}.{ref_domain_key}' is incorrect: "
                        f"{ref_step_id} produces '{expected_key}', not '{ref_domain_key}'. "
                        f"Use '$steps.{correct_step_id}.{ref_domain_key}' instead."
                    )
                else:
                    errors.append(
                        f"Reference '$steps.{ref_step_id}.{ref_domain_key}' is incorrect: "
                        f"{ref_step_id} produces '{expected_key}', not '{ref_domain_key}'. "
                        f"No step in the plan produces '{ref_domain_key}'."
                    )

    if errors:
        feedback = (
            "GHOST_DEPENDENCY ERROR - Incorrect $steps references detected:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nFix: Use the correct step_id for each result_key. "
            "Each tool produces data under its result_key (from catalogue)."
        )
        return False, feedback

    return True, None


# ============================================================================
# Insufficient Content Detection
# ============================================================================
# Pre-LLM detection of missing content for mutation operations.
# Triggers HITL clarification when user hasn't provided enough info.
# Example: "send an email to marie" without body/subject.
#
# Configuration:
# - Feature flag: INSUFFICIENT_CONTENT_DETECTION_ENABLED (settings)
# - Min chars threshold: INSUFFICIENT_CONTENT_MIN_CHARS_THRESHOLD (settings)
# - Tool patterns: INSUFFICIENT_CONTENT_TOOL_PATTERNS (constants.py)
# - Detection patterns: HitlMessages.get_insufficient_content_patterns() (i18n)
# ============================================================================


def detect_early_insufficient_content(
    query_intelligence: Any,
    user_request: str,
    user_language: str = settings.default_language,
) -> SemanticValidationResult | None:
    """
    Pre-planner detection of insufficient content using QueryIntelligence.

    OPTIMIZATION: Detects missing content BEFORE the planner LLM is called,
    saving ~5,000-10,000 tokens per request when clarification is needed.

    Without early detection:
        1. Planner call #1 → incomplete plan (e.g., only get_contacts)
        2. Semantic validator → scope_underflow detected
        3. Planner call #2 → complete plan but missing params
        4. detect_insufficient_content() → FINALLY triggers clarification
        Total: 2 planner LLM calls (~10,000 tokens) before clarification

    WITH early detection:
        1. detect_early_insufficient_content() → detects missing content
        2. Returns clarification result immediately
        Total: 0 planner LLM calls before clarification

    Args:
        query_intelligence: QueryIntelligence object or dict with:
            - domains: Detected domains (e.g., ['emails', 'contacts'])
            - immediate_intent: Detected intent (e.g., 'send', 'create')
        user_request: Original user message (English after Semantic Pivot)
        user_language: User's language for i18n questions

    Returns:
        SemanticValidationResult with requires_clarification=True if insufficient,
        None if content sufficient or early detection not applicable.
    """
    from src.core.constants import (
        EARLY_DETECTION_CONTENT_FIELDS,
        EARLY_DETECTION_DOMAIN_MAP,
        EARLY_DETECTION_MUTATION_INTENTS,
        EARLY_DETECTION_SKIP_FIELDS,
        INSUFFICIENT_CONTENT_REQUIRED_FIELDS,
    )
    from src.core.i18n_hitl import EARLY_RECIPIENT_PATTERNS

    # NOTE: Insufficient content detection is always enabled

    if query_intelligence is None:
        return None

    # Extract fields from QueryIntelligence (handle dict and object)
    if isinstance(query_intelligence, dict):
        domains = query_intelligence.get("domains", [])
        intent = query_intelligence.get("immediate_intent", "")
    else:
        domains = getattr(query_intelligence, "domains", [])
        intent = getattr(query_intelligence, "immediate_intent", "")

    intent_lower = (intent or "").lower()

    # Only trigger for mutation intents
    if intent_lower not in EARLY_DETECTION_MUTATION_INTENTS:
        return None

    # Find matching insufficient_content_domain from (domain, intent)
    insufficient_domain = None
    for domain in domains:
        domain_lower = (domain or "").lower()
        key = (domain_lower, intent_lower)
        if key in EARLY_DETECTION_DOMAIN_MAP:
            insufficient_domain = EARLY_DETECTION_DOMAIN_MAP[key]
            break

    if not insufficient_domain:
        return None

    # Get required fields for this domain
    required_fields = INSUFFICIENT_CONTENT_REQUIRED_FIELDS.get(insufficient_domain, [])
    if not required_fields:
        return None

    # Sort by priority (lowest = first to ask)
    sorted_fields = sorted(required_fields, key=lambda f: f.get("priority", 99))
    min_chars = settings.insufficient_content_min_chars_threshold
    user_request_lower = user_request.lower()

    for field_def in sorted_fields:
        field_name = field_def["field"]
        is_required = field_def.get("required", True)

        if not is_required:
            continue

        # Skip fields handled by planner defaults
        if field_name in EARLY_DETECTION_SKIP_FIELDS:
            continue

        # Check recipient field (email-specific)
        if field_name == "recipient":
            has_recipient = any(p in user_request_lower for p in EARLY_RECIPIENT_PATTERNS)
            if has_recipient or "@" in user_request:
                continue
            # No recipient found - return clarification
            logger.info(
                "early_insufficient_content_missing_recipient",
                domain=insufficient_domain,
                user_request_preview=user_request[:50],
            )
            return _create_field_clarification_result(
                domain=insufficient_domain,
                field_name=field_name,
                field_def=field_def,
                user_language=user_language,
            )

        # Check content fields (body, subject, title, name)
        # These are free-text fields where user must provide composed content
        if field_name in EARLY_DETECTION_CONTENT_FIELDS:
            has_inline = _check_request_has_inline_content(
                user_request=user_request,
                domain=insufficient_domain,
                min_chars_threshold=min_chars,
            )
            if has_inline:
                continue
            # No inline content - return clarification
            logger.info(
                "early_insufficient_content_missing_content",
                domain=insufficient_domain,
                field=field_name,
                user_request_preview=user_request[:50],
            )
            return _create_field_clarification_result(
                domain=insufficient_domain,
                field_name=field_name,
                field_def=field_def,
                user_language=user_language,
            )

    # All required fields appear to be present
    return None


def detect_insufficient_content(
    plan: ExecutionPlan,
    user_request: str,
    user_language: str = settings.default_language,
) -> SemanticValidationResult | None:
    """
    Detect if a mutation tool is called without sufficient content.

    This is a pre-LLM check that catches obvious cases where the user
    hasn't provided enough information for a mutation operation.

    Detection logic (v2 - RECURSIVE field-by-field):
    1. Identify the domain from the tool name
    2. Get required fields for that domain, sorted by priority
    3. Check each field in priority order
    4. Return clarification for the FIRST missing REQUIRED field
    5. After user responds, flow re-runs and checks next missing field

    This enables multi-turn clarification without complex state management.

    NOTE: Insufficient content detection is always enabled.
    Threshold controlled via settings.insufficient_content_min_chars_threshold.

    Args:
        plan: ExecutionPlan to check
        user_request: Original user message (may contain implicit content)
        user_language: User's language for i18n questions

    Returns:
        SemanticValidationResult with requires_clarification=True if insufficient,
        None if content is sufficient, not applicable, or feature disabled.

    Example:
        >>> plan = ExecutionPlan(steps=[Step(tool="send_email_draft", params={"to": "marie"})])
        >>> result = detect_insufficient_content(plan, "send an email to marie", "fr")
        >>> result.requires_clarification  # True
        >>> result.clarification_questions  # ["What would you like to write in this email?"]
    """
    from src.core.constants import (
        INSUFFICIENT_CONTENT_REQUIRED_FIELDS,
        INSUFFICIENT_CONTENT_TOOL_PATTERNS,
    )

    # NOTE: Insufficient content detection is always enabled

    for i, step in enumerate(plan.steps):
        tool_name = (step.tool_name or "").lower()
        params = step.parameters or {}

        # Find matching tool pattern from centralized constants
        for tool_pattern, domain in INSUFFICIENT_CONTENT_TOOL_PATTERNS.items():
            if tool_pattern in tool_name:
                # Get required fields for this domain, sorted by priority
                required_fields = INSUFFICIENT_CONTENT_REQUIRED_FIELDS.get(domain, [])
                if not required_fields:
                    continue

                # Sort by priority (lowest = first to ask)
                sorted_fields = sorted(required_fields, key=lambda f: f.get("priority", 99))

                # Check each field in priority order
                for field_def in sorted_fields:
                    field_name = field_def["field"]
                    param_names = field_def["param_names"]
                    is_required = field_def.get("required", True)

                    # Only check required fields for clarification trigger
                    if not is_required:
                        continue

                    # Check if ANY param name for this field has a value
                    field_has_value = _check_field_has_value(params, param_names)

                    # If no value in params, check if user provided inline content
                    # Example: "send an email to marie to wish her happy birthday"
                    # The "to wish her..." part IS the content
                    if not field_has_value and field_name in ("body", "subject", "title"):
                        min_chars = settings.insufficient_content_min_chars_threshold
                        has_inline = _check_request_has_inline_content(
                            user_request=user_request,
                            domain=domain,
                            min_chars_threshold=min_chars,
                        )
                        if has_inline:
                            # User provided inline content, skip this field
                            logger.debug(
                                "insufficient_content_inline_detected",
                                domain=domain,
                                field=field_name,
                                user_request_preview=user_request[:50],
                            )
                            continue

                    if not field_has_value:
                        # First missing required field found - return clarification
                        return _create_field_clarification_result(
                            domain=domain,
                            field_name=field_name,
                            field_def=field_def,
                            user_language=user_language,
                            step_index=i,
                            tool_name=tool_name,
                        )

                # All required fields present for this tool
                break

    return None


def _check_field_has_value(params: dict[str, Any], param_names: list[str]) -> bool:
    """
    Check if any parameter name for a field has a non-empty value.

    Args:
        params: Step parameters dict
        param_names: List of parameter names that satisfy this field

    Returns:
        True if at least one param has a non-empty value
    """
    for param in param_names:
        value = params.get(param)
        if value is not None:
            # Handle different value types
            if isinstance(value, str) and value.strip():
                return True
            elif isinstance(value, list | dict) and value:
                return True
            elif isinstance(value, int | float | bool):
                return True  # Numeric/bool values are always "present"
    return False


def _check_request_has_inline_content(
    user_request: str,
    domain: str,
    min_chars_threshold: int,
) -> bool:
    """
    Check if user's request contains inline content beyond trigger patterns.

    Example: "envoie un email à marie pour lui souhaiter bon anniversaire"
    After removing "envoie un email à marie", the remaining
    "pour lui souhaiter bon anniversaire" IS the content.

    Args:
        user_request: Original user message
        domain: Domain for pattern lookup (email, event, task, contact)
        min_chars_threshold: Minimum chars remaining to consider as content

    Returns:
        True if request has sufficient inline content
    """
    from src.core.i18n_hitl import HitlMessages

    # Get internationalized detection patterns for this domain
    detection_patterns = HitlMessages.get_insufficient_content_patterns(domain)

    if not detection_patterns:
        # No patterns for this domain - can't determine inline content
        return False

    request_lower = user_request.lower()
    remaining = request_lower

    # Remove all trigger patterns to see what's left
    for pattern in detection_patterns:
        remaining = remaining.replace(pattern.lower(), "").strip()

    # If substantial content remains, consider it inline content
    # Example: "to wish her happy birthday" (>30 chars) -> sufficient
    return len(remaining) > min_chars_threshold


def _create_field_clarification_result(
    domain: str,
    field_name: str,
    field_def: dict[str, Any],
    user_language: str,
    step_index: int | None = None,
    tool_name: str | None = None,
) -> SemanticValidationResult:
    """
    Create a SemanticValidationResult for a specific missing field.

    Uses field-specific i18n questions and includes enumerated options
    when applicable (e.g., priority field for tasks).

    Args:
        domain: Domain (email, event, task, contact)
        field_name: The specific field that's missing
        field_def: Field definition with options, required, etc.
        user_language: User's language for i18n
        step_index: Index of the step in the plan (0-based), None for early detection
        tool_name: Name of the tool requiring clarification, None for early detection

    Returns:
        SemanticValidationResult with field-specific clarification question
    """
    from src.core.i18n_hitl import HitlMessages

    # Get field-specific question with options if applicable
    question = HitlMessages.format_field_question_with_options(
        domain=domain,
        field=field_name,
        language=user_language,
    )

    # Get options for metadata (used by frontend for UI)
    options = HitlMessages.get_field_options(domain, field_name, user_language)

    logger.info(
        "insufficient_content_field_missing",
        step_index=step_index,
        tool_name=tool_name,
        domain=domain,
        missing_field=field_name,
        field_priority=field_def.get("priority"),
        has_options=options is not None,
        user_language=user_language,
    )

    issue = SemanticIssue(
        issue_type=SemanticIssueType.INSUFFICIENT_CONTENT,
        description=f"Missing required field '{field_name}' for {domain} operation",
        step_index=step_index,
        severity="medium",
        suggested_fix=f"User must provide {field_name}",
    )

    return SemanticValidationResult(
        is_valid=False,
        issues=[issue],
        confidence=1.0,
        requires_clarification=True,
        clarification_questions=[question],
        validation_duration_seconds=0.0,
        criticality=CriticalityLevel.LOW,
        used_fallback=False,
        clarification_field=field_name,  # Store what field was asked for
    )


# ============================================================================
# Semantic Validator
# ============================================================================


class PlanSemanticValidator:
    """
    LLM-based semantic validation for execution plans.

    Validates that plans match user intent by checking for:
    - Cardinality issues (single op vs "pour chaque")
    - Missing dependencies
    - Implicit assumptions
    - Scope mismatches

    Best Practices (LangChain v1.0 / LangGraph v1.0):
        - Uses distinct LLM from planner (avoids bias)
        - with_structured_output() for reliable parsing
        - Short-circuits trivial plans (performance)
        - Timeout protection with fallback
        - Feature flag controlled

    Example:
        >>> validator = PlanSemanticValidator()
        >>> result = await validator.validate(
        ...     plan=execution_plan,
        ...     user_request="Envoie un email à tous mes contacts",
        ...     user_language="fr",
        ... )
        >>> if result.requires_clarification:
        ...     for question in result.clarification_questions:
        ...         print(question)
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        provider: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        """
        Initialize semantic validator.

        Args:
            llm: Optional LLM instance. If None, uses default semantic validator LLM.
            provider: Optional provider name. If None, uses default from settings.
            timeout_seconds: Validation timeout. If None, uses settings.semantic_validation_timeout_seconds
        """
        self._llm = llm
        from src.core.llm_config_helper import get_llm_config_for_agent

        self._provider = (
            provider or get_llm_config_for_agent(settings, "semantic_validator").provider
        )
        self._timeout_seconds = timeout_seconds or settings.semantic_validation_timeout_seconds

        # Lazy initialization of LLM
        if self._llm is None:
            self._llm = get_llm("semantic_validator")

        logger.debug(
            "semantic_validator_initialized",
            provider=self._provider,
            timeout_seconds=self._timeout_seconds,
        )

    async def validate(
        self,
        plan: ExecutionPlan,
        user_request: str,
        user_language: str = settings.default_language,
        config: Any | None = None,
        query_intelligence: Any | None = None,
        original_request: str | None = None,
    ) -> SemanticValidationResult:
        """
        Validate plan semantic coherence with user request.

        Gold Grade Features:
            - Short-circuit for plans ≤1 step (trivial cases)
            - Timeout protection (optimistic validation)
            - Fallback to "valid" if validation fails (fail-open)
            - Feature flag controlled

        Args:
            plan: ExecutionPlan to validate
            user_request: User message (English pivot when available)
            user_language: User language (fr, en, es)
            config: Optional RunnableConfig for LangGraph
            original_request: The user's ORIGINAL message when user_request is
                the English pivot — authoritative for content/names/language

        Returns:
            SemanticValidationResult with validation outcome

        Performance:
            - Target: P95 < 2s
            - Timeout: 1s (fail-open fallback)
            - Short-circuit: ≤1 step → instant pass
        """
        start_time = time.time()

        # NOTE: Semantic validation is always enabled

        # =====================================================================
        # INSUFFICIENT CONTENT CHECK: Pre-LLM detection of missing content
        # =====================================================================
        # Check if mutation tools are called without sufficient content.
        # This triggers HITL clarification BEFORE attempting to execute.
        # Example: "send an email to marie" without body/subject
        # =====================================================================
        insufficient_result = detect_insufficient_content(
            plan=plan,
            user_request=user_request,
            user_language=user_language,
        )
        if insufficient_result:
            logger.info(
                "semantic_validation_insufficient_content",
                step_count=len(plan.steps),
                duration_ms=int((time.time() - start_time) * 1000),
            )
            # Update duration before returning
            insufficient_result.validation_duration_seconds = time.time() - start_time
            return insufficient_result

        # =====================================================================
        # $STEPS REFERENCE VALIDATION: Pre-LLM detection of ghost dependencies
        # =====================================================================
        # Check if $steps references use correct result_keys for each step.
        # Example error: $steps.step_2.events when step_2 is get_weather_tool
        # (which produces "weathers", not "events").
        # This triggers REJECT status to force re-planning with correct refs.
        # =====================================================================
        refs_valid, refs_feedback = validate_steps_references(plan)
        if not refs_valid:
            logger.warning(
                "semantic_validation_ghost_dependency",
                step_count=len(plan.steps),
                feedback_preview=refs_feedback[:100] if refs_feedback else "",
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return _programmatic_rejection(
                SemanticIssueType.GHOST_DEPENDENCY,
                "$steps reference uses wrong result_key for step",
                refs_feedback or "Fix $steps references",
                CriticalityLevel.HIGH,
                start_time,
            )

        # =====================================================================
        # PLACEHOLDER CONTACT VALIDATION: Pre-LLM detection of fabricated emails
        # =====================================================================
        # The planner must NEVER invent contact details. Observed in prod
        # (2026-07-17): attendees=['jane.doe@example.com'] fabricated for
        # a real contact. RFC 2606 reserved domains in a non-free-text mutation
        # parameter are always an hallucination → deterministic REJECT with
        # replanning feedback (resolve via contacts step or omit).
        # =====================================================================
        placeholder_findings = detect_placeholder_contacts(plan)
        if placeholder_findings:
            logger.warning(
                "semantic_validation_placeholder_contact",
                findings_count=len(placeholder_findings),
                step_count=len(plan.steps),
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return _programmatic_rejection(
                SemanticIssueType.WRONG_PARAMETERS,
                (
                    "Fabricated placeholder contact detail: "
                    f"{'; '.join(placeholder_findings[:3])}"
                ),
                (
                    "NEVER invent contact details (emails, phone numbers). "
                    "Either add a get_contacts_tool step and reference its "
                    "output ($steps.step_N.contacts[0].emailAddresses[0].value), "
                    "or OMIT the optional parameter entirely."
                ),
                CriticalityLevel.HIGH,
                start_time,
            )

        # =====================================================================
        # FOR_EACH PATTERN VALIDATION: Check for_each coherence with user intent
        # =====================================================================
        # Validates that:
        # 1. If user said "each", plan has for_each step
        # 2. for_each_max is sufficient for expected cardinality
        # 3. for_each references point to valid steps
        # =====================================================================
        for_each_valid, for_each_feedback, for_each_issue = validate_for_each_patterns(
            plan=plan,
            query_intelligence=query_intelligence,
        )
        if not for_each_valid and for_each_issue:
            logger.warning(
                "semantic_validation_for_each_error",
                step_count=len(plan.steps),
                issue_type=for_each_issue.value,
                feedback_preview=for_each_feedback[:100] if for_each_feedback else "",
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return _programmatic_rejection(
                for_each_issue,
                "for_each pattern issue detected",
                for_each_feedback or "Fix for_each configuration",
                CriticalityLevel.MEDIUM,
                start_time,
            )

        # =====================================================================
        # READ INTENT vs WRITING PLAN: the plan acts when nobody asked it to
        # =====================================================================
        # Prod 2026-08-01: "de quand date mon dernier appel à ma femme ?" was
        # planned as get_contacts_tool -> place_phone_call_tool("vérifier la
        # date du dernier appel"). The user asked WHEN; the plan was to phone
        # her and ask. Nothing caught it: the trigger below skips a two-step,
        # $steps-chained, mutation-ending plan as `well_formed_cross_domain_
        # mutation` — the better formed the plan, the less it was reviewed.
        #
        # So this runs BEFORE the trigger, with the other deterministic rules:
        # no LLM, no token cost, and out of reach of that exemption. Mirror of
        # `mutation_intent_but_no_mutation_tool`, which had no counterpart in
        # this direction.
        # =====================================================================
        writing_tools = plan_writes_without_write_intent(plan, query_intelligence)
        if writing_tools:
            logger.warning(
                "semantic_validation_write_without_intent",
                step_count=len(plan.steps),
                writing_tools=writing_tools,
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return _programmatic_rejection(
                SemanticIssueType.SCOPE_OVERFLOW,
                (
                    "The request asks for information, but the plan performs "
                    f"action(s): {', '.join(writing_tools)}"
                ),
                (
                    "The user asked a QUESTION, not for an action. Answer it by "
                    "READING: keep the lookup steps and replace every action tool "
                    f"({', '.join(writing_tools)}) with a read tool of the same "
                    "domain. Never contact anyone to obtain information the "
                    "system can read itself."
                ),
                CriticalityLevel.HIGH,
                start_time,
            )

        # =====================================================================
        # PATTERN LEARNING BYPASS: High-confidence patterns skip LLM validation
        # =====================================================================
        # If this plan pattern has been validated successfully many times (>90%
        # confidence with 10+ observations), we bypass the expensive LLM call.
        # This dramatically reduces latency and cost for common patterns.
        #
        # SECURITY FIX 2026-01-14: Now passes query_intelligence to verify that
        # the stored pattern's domains and intent match the current query.
        # This prevents incorrect bypass for mismatched patterns (e.g., read
        # pattern bypassing validation for a mutation query).
        # =====================================================================
        from src.domains.agents.services.plan_pattern_learner import can_skip_validation

        try:
            if await can_skip_validation(plan, query_intelligence):
                logger.info(
                    "semantic_validation_bypassed_learned_pattern",
                    step_count=len(plan.steps),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
                return self._create_valid_result(
                    "Validation bypassed: learned pattern with high confidence",
                    duration=time.time() - start_time,
                )
        except Exception as e:
            # Fail-open: if pattern check fails, continue with normal validation
            logger.debug(f"Pattern bypass check failed: {e}")

        # Smart trigger: only validate when beneficial
        # This replaces the simple "≤1 step" check with intelligent analysis
        # v3.1: Pass query_intelligence for LLM-detected flags (mutation, cardinality)
        should_validate, trigger_reason = should_trigger_semantic_validation(
            plan=plan,
            user_request=user_request,
            planner_confidence=1.0,  # Can be passed from planner in future
            query_intelligence=query_intelligence,
        )

        if not should_validate:
            logger.info(
                "semantic_validation_skipped",
                reason=trigger_reason,
                step_count=len(plan.steps),
            )
            return self._create_valid_result(
                f"Validation skipped: {trigger_reason}",
                duration=time.time() - start_time,
            )

        # Validation triggered - log the reason
        logger.info(
            "semantic_validation_triggered",
            reason=trigger_reason,
            step_count=len(plan.steps),
        )

        # Async validation with timeout
        try:
            try:
                result = await asyncio.wait_for(
                    self._validate_with_llm(
                        plan, user_request, user_language, config, original_request
                    ),
                    timeout=self._timeout_seconds,
                )
            except StructuredOutputError as first_error:
                # deepseek-v4-flash keeps a residual empty-answer rate on this
                # call (measured 2/9 on 2026-07-17 even after the prompt-conflict
                # fix): ONE retry squares the residual (~4 %) before the
                # fail-open fallback below would give the plan a free pass.
                logger.warning(
                    "semantic_validation_retry",
                    error_type=type(first_error).__name__,
                    raw_output_length=len(getattr(first_error, "raw_output", None) or ""),
                )
                result = await asyncio.wait_for(
                    self._validate_with_llm(
                        plan, user_request, user_language, config, original_request
                    ),
                    timeout=self._timeout_seconds,
                )

            duration = time.time() - start_time

            # Import metrics locally to avoid circular imports
            from src.infrastructure.observability.metrics_agents import (
                semantic_validation_duration_seconds,
                semantic_validation_total,
            )

            semantic_validation_duration_seconds.observe(duration)
            semantic_validation_total.labels(result="valid" if result.is_valid else "invalid").inc()

            # Dashboard 16 "Semantic Validation Issues" panel — non-critical
            with suppress(Exception):
                from src.infrastructure.observability.metrics_agents import (
                    semantic_validation_issues_detected,
                )

                for _issue in result.issues:
                    _issue_type = getattr(_issue, "issue_type", None) or (
                        _issue.get("issue_type") if isinstance(_issue, dict) else "unknown"
                    )
                    semantic_validation_issues_detected.labels(issue_type=str(_issue_type)).inc()

            logger.info(
                "semantic_validation_complete",
                is_valid=result.is_valid,
                issue_count=len(result.issues),
                requires_clarification=result.requires_clarification,
                duration_seconds=duration,
            )

            return result

        except TimeoutError:
            # Timeout: Fail-open with fallback (optimistic validation)
            # IMPORTANT: Reduced confidence (0.3) + fallback_reason for UI notification
            duration = time.time() - start_time

            from src.infrastructure.observability.metrics_agents import (
                semantic_validation_timeout_total,
            )

            semantic_validation_timeout_total.inc()

            logger.warning(
                "semantic_validation_timeout_fallback",
                timeout_seconds=self._timeout_seconds,
                duration_seconds=duration,
            )

            # Return with explicit fallback reason for UI notification
            return SemanticValidationResult(
                is_valid=True,  # Fail-open for UX
                issues=[],
                confidence=0.3,  # Reduced confidence (was 0.5 via _create_valid_result)
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=duration,
                criticality=CriticalityLevel.MEDIUM,  # Elevate criticality for unvalidated plans
                used_fallback=True,
                fallback_reason="validation_timeout",
            )

        except Exception as e:
            # Error: Fail-open with fallback
            # IMPORTANT: Reduced confidence (0.3) + fallback_reason for UI notification
            duration = time.time() - start_time

            # StructuredOutputError carries the raw model text the rescue failed
            # on. Its LENGTH is the key diagnostic at ERROR (0 = the model went
            # silent — the 2026-07-17 prompt-conflict signature); the payload
            # itself may echo user text, so it stays at DEBUG (PII rule).
            raw_output = getattr(e, "raw_output", None)
            logger.error(
                "semantic_validation_error_fallback",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=duration,
                raw_output_length=len(raw_output) if raw_output else 0,
                exc_info=True,
            )
            if raw_output:
                logger.debug("semantic_validation_raw_output", raw_output=raw_output[:500])

            # Return with explicit fallback reason for UI notification
            return SemanticValidationResult(
                is_valid=True,  # Fail-open for UX
                issues=[],
                confidence=0.3,  # Reduced confidence
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=duration,
                criticality=CriticalityLevel.MEDIUM,  # Elevate criticality for unvalidated plans
                used_fallback=True,
                fallback_reason=f"validation_error:{type(e).__name__}",
            )

    async def _validate_with_llm(
        self,
        plan: ExecutionPlan,
        user_request: str,
        user_language: str,
        config: Any | None,
        original_request: str | None = None,
    ) -> SemanticValidationResult:
        """
        Perform actual LLM-based validation.

        Uses structured output for reliable parsing.

        Args:
            plan: ExecutionPlan to validate
            user_request: Original user message
            user_language: User language
            config: Optional RunnableConfig

        Returns:
            SemanticValidationResult
        """
        # Build validation prompt
        messages = self._build_validation_prompt(
            plan, user_request, user_language, original_request=original_request
        )

        # DEBUG: verify TokenTrackingCallback presence. LangChain v1 callback
        # managers expose `.handlers` (not directly iterable); raw lists pass
        # through; anything else counts as none.
        if config:
            callbacks = (
                config.get("callbacks", [])
                if isinstance(config, dict)
                else getattr(config, "callbacks", [])
            )
            callback_list = getattr(
                callbacks, "handlers", callbacks if isinstance(callbacks, list) else []
            )
            callback_types = [type(cb).__name__ for cb in callback_list]
            logger.debug(
                "semantic_validator_config_callbacks",
                has_config=True,
                callback_count=len(callback_list),
                callback_types=callback_types,
                has_token_tracking="TokenTrackingCallback" in callback_types,
            )
        else:
            logger.warning(
                "semantic_validator_no_config",
                msg="No config passed to semantic_validator - tokens may not be tracked",
            )

        # Call LLM with structured output
        start_time = time.time()

        try:
            output: SemanticValidationOutput = await get_structured_output(
                llm=self._llm,
                messages=messages,
                schema=SemanticValidationOutput,
                provider=self._provider,
                node_name="semantic_validator",
                config=config,
            )

            duration = time.time() - start_time

            logger.debug(
                "semantic_validation_llm_complete",
                is_valid=output.is_valid,
                confidence=output.confidence,
                issue_count=len(output.issues),
                duration_seconds=duration,
            )

            # Convert to domain model
            # Note: Order matches dataclass definition - required fields first, then optional
            #
            # Clarification Logic (Issue #60 tuning):
            # Only require clarification if:
            # 1. There are clarification questions from LLM
            # 2. Confidence is below threshold (configurable)
            # 3. There are actual issues detected
            # This prevents over-questioning on minor ambiguities
            has_questions = len(output.clarification_questions) > 0
            has_issues = len(output.issues) > 0
            low_confidence = output.confidence < settings.semantic_validation_confidence_threshold

            # Require clarification only for significant issues with low confidence
            requires_clarification = has_questions and has_issues and low_confidence

            logger.debug(
                "semantic_validation_clarification_decision",
                has_questions=has_questions,
                has_issues=has_issues,
                confidence=output.confidence,
                threshold=settings.semantic_validation_confidence_threshold,
                low_confidence=low_confidence,
                requires_clarification=requires_clarification,
            )

            return SemanticValidationResult(
                is_valid=output.is_valid,
                issues=output.issues,
                confidence=output.confidence,
                requires_clarification=requires_clarification,
                clarification_questions=(
                    output.clarification_questions if requires_clarification else []
                ),
                validation_duration_seconds=duration,
                criticality=output.criticality,  # Optional with default
                used_fallback=False,
            )

        except Exception as e:
            # Re-raise for timeout/error handling in validate()
            logger.error(
                "semantic_validation_llm_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _build_validation_prompt(
        self,
        plan: ExecutionPlan,
        user_request: str,
        user_language: str,
        original_request: str | None = None,
    ) -> list:
        """
        Build validation prompt for LLM.

        Uses externalized prompt from versioned file for:
        - A/B testing different prompt versions
        - Easy iteration without code changes
        - Consistent prompt management across all LLMs

        IMPORTANT (Issue #60 Fix):
        Provides complete plan details including:
        - Full parameters with values (for cardinality detection)
        - Dependencies between steps (for ghost dependency detection)
        - Step descriptions (for intent matching)
        - Execution metadata (estimated cost, timeout)

        Args:
            plan: ExecutionPlan to validate
            user_request: Original user message
            user_language: User language

        Returns:
            List of LangChain messages
        """
        # Load versioned system prompt (cached via LRU)
        system_prompt = load_prompt(
            "semantic_validator_prompt", version=settings.semantic_validator_prompt_version
        )

        # Build detailed plan representation for LLM
        plan_details = self._format_plan_for_validation(plan)

        # Runtime defect 2026-07-30 (peers program): with only the English
        # pivot on display, the validator flagged FRENCH content args, folded
        # recipient names and a phantom "reply id". When the original differs,
        # it is shown as the AUTHORITY for content, names and language.
        original_block = request_label = ""
        if original_request and original_request.strip() != user_request.strip():
            request_label = " (English translation, for capability matching only)"
            original_block = f"""

## Original User Message (AUTHORITATIVE for content, names and language)
"{original_request}"
Content parameters (message, body, description…) must carry THIS intent and language — never flag a content parameter for differing from the English translation above.
Rephrasing indirect speech into direct address ("ask him how he is" → message "how are you?") is expected and correct.
Names resolved from the user's own data are matched accent- and case-insensitively: an accent difference is NOT an issue."""

        # Build human message with complete plan context
        human_content = f"""## User Request{request_label}
"{user_request}"{original_block}

## Execution Plan
{plan_details}

## Validation Context
- User Language: {user_language}
- Total Steps: {len(plan.steps)}
- Execution Mode: {plan.execution_mode}
- Estimated Cost: ${plan.estimated_cost_usd:.4f} USD

## Your Task
Validate this plan against the user request. Pay special attention to:
1. **Cardinality**: Does "pour chaque"/"for each"/"tous"/"all" in user request match plan structure?
2. **Parameters**: Do the numeric values (max_results, limits) match user expectations?
3. **Dependencies**: Are step dependencies correctly defined?
4. **Completeness**: Does the plan fully address the user request?

Deliver your verdict ONLY by calling the structured validation tool — never as a text answer. Write the free-text fields of the tool payload (issues, questions) in {user_language}."""

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content),
        ]

    def _format_plan_for_validation(self, plan: ExecutionPlan) -> str:
        """
        Format execution plan for semantic validation prompt.

        Creates a detailed, structured representation of the plan that enables
        the LLM to detect semantic issues like cardinality mismatches.

        Issue #60: This format explicitly shows:
        - Exact parameter values (for cardinality detection: max_results=20 vs "2 per contact")
        - Step dependencies (for ghost dependency detection)
        - Step descriptions (for intent matching)
        - Agent assignments (for scope validation)

        Args:
            plan: ExecutionPlan to format

        Returns:
            Formatted string representation of the plan
        """
        lines = []

        for i, step in enumerate(plan.steps):
            # Step header with index and ID
            lines.append(f"### Step {i} (id: {step.step_id})")

            # Core fields
            lines.append(f"- **Type**: {step.step_type.value}")
            if step.agent_name:
                lines.append(f"- **Agent**: {step.agent_name}")
            if step.tool_name:
                lines.append(f"- **Tool**: {step.tool_name}")

            # Description (important for intent matching)
            if step.description:
                lines.append(f"- **Description**: {step.description}")

            # Parameters (CRITICAL for cardinality detection)
            if step.parameters:
                lines.append("- **Parameters**:")
                for key, value in step.parameters.items():
                    # Format value for readability
                    if isinstance(value, str) and value.startswith("$steps"):
                        # Reference to previous step output
                        lines.append(f"    - {key}: `{value}` (reference)")
                    elif isinstance(value, list):
                        lines.append(f"    - {key}: {value} (list, count={len(value)})")
                    elif isinstance(value, int):
                        # Numeric values are crucial for cardinality
                        lines.append(f"    - {key}: {value} (number)")
                    else:
                        lines.append(f"    - {key}: {value!r}")

            # FOR_EACH iteration pattern (CRITICAL for cardinality validation)
            # The presence of for_each indicates the step will iterate over a collection
            if step.for_each:
                lines.append(f"- **For Each**: `{step.for_each}` (iteration over collection)")
                if step.for_each_max:
                    lines.append(f"- **For Each Max**: {step.for_each_max} items")
                lines.append(
                    "  → This step will execute ONCE PER ITEM in the referenced collection"
                )

            # Dependencies (for ghost dependency detection)
            if step.depends_on:
                lines.append(f"- **Depends on**: {step.depends_on}")

            # HITL requirements
            if step.approvals_required:
                lines.append("- **Requires Approval**: Yes (HITL)")

            # Conditional logic
            if step.condition:
                lines.append(f"- **Condition**: {step.condition}")
                if step.on_success:
                    lines.append(f"- **On Success**: go to {step.on_success}")
                if step.on_fail:
                    lines.append(f"- **On Fail**: go to {step.on_fail}")

            lines.append("")  # Blank line between steps

        return "\n".join(lines)

    def _create_valid_result(
        self,
        reason: str,
        duration: float,
        used_fallback: bool = False,
    ) -> SemanticValidationResult:
        """
        Create a "valid" validation result (for short-circuits and fallbacks).

        Args:
            reason: Reason for validity
            duration: Validation duration
            used_fallback: True if this is a fallback result

        Returns:
            SemanticValidationResult marked as valid
        """
        return SemanticValidationResult(
            is_valid=True,
            issues=[],
            confidence=(
                1.0 if not used_fallback else settings.semantic_validation_fallback_confidence
            ),
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=duration,
            criticality=CriticalityLevel.LOW,  # Optional with default
            used_fallback=used_fallback,
        )
