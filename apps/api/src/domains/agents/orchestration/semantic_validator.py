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
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import (
    CARDINALITY_ALL,
    FOR_EACH_ITEM_REF,
    TOOL_NAME_DELEGATE_SUB_AGENT,
)
from src.domains.agents.prompts import load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.logging import get_logger

from .plan_schemas import ExecutionPlan

logger = get_logger(__name__)


# ============================================================================
# Semantic Issue Types
# ============================================================================


class SemanticIssueType(str, Enum):
    """
    Types of semantic issues detected in execution plans.

    The "Seven Deadly Sins" of plan validation - each represents a specific
    class of plan-request mismatch that may require correction or clarification.

    Critical Issues (blocking):
        HALLUCINATED_CAPABILITY: Tool/parameter doesn't exist in available_tools
        GHOST_DEPENDENCY: Step references non-existent output from another step
        LOGICAL_CYCLE: Circular dependencies or deadlock conditions

    Semantic Issues:
        CARDINALITY_MISMATCH: Plan processes one item when user said "all" or vice versa
        SCOPE_OVERFLOW: Plan does more than requested (scope creep)
        SCOPE_UNDERFLOW: Plan ignores constraints or does less than requested (lazy execution)

    Safety Issues:
        DANGEROUS_AMBIGUITY: High-stakes action based on vague input without confirmation
        IMPLICIT_ASSUMPTION: Plan assumes data exists without verification
    """

    # Critical - Plan cannot execute correctly
    HALLUCINATED_CAPABILITY = "hallucinated_capability"
    GHOST_DEPENDENCY = "ghost_dependency"
    LOGICAL_CYCLE = "logical_cycle"

    # Semantic - Plan may not match intent
    CARDINALITY_MISMATCH = "cardinality_mismatch"
    SCOPE_OVERFLOW = "scope_overflow"
    SCOPE_UNDERFLOW = "scope_underflow"
    WRONG_PARAMETERS = "wrong_parameters"  # Parameter values don't match user intent
    MISSING_STEP = "missing_step"  # Plan is missing a necessary step

    # Safety - Plan may cause unintended consequences
    DANGEROUS_AMBIGUITY = "dangerous_ambiguity"
    IMPLICIT_ASSUMPTION = "implicit_assumption"

    # Content - User hasn't provided sufficient content for mutation
    INSUFFICIENT_CONTENT = "insufficient_content"

    # FOR_EACH pattern issues (plan_planner.md Section 10)
    FOR_EACH_MISSING_CARDINALITY = (
        "for_each_missing_cardinality"  # User said "each" but no for_each
    )
    FOR_EACH_MAX_EXCEEDED = "for_each_max_exceeded"  # for_each_max too small for expected items
    FOR_EACH_INVALID_REFERENCE = "for_each_invalid_reference"  # for_each points to non-array
    FOR_EACH_MISSING_ITEM_REF = "for_each_missing_item_ref"  # Parameters don't use $item references

    # Legacy aliases (for backward compatibility)
    MISSING_DEPENDENCY = "ghost_dependency"  # Alias
    AMBIGUOUS_INTENT = "dangerous_ambiguity"  # Alias


# ============================================================================
# Pydantic Schemas for Structured Output
# ============================================================================


class SemanticIssue(BaseModel):
    """
    A single semantic issue detected in the plan.

    Used in structured LLM output for reliable parsing.
    Aligned with "Seven Deadly Sins" taxonomy from semantic_validator_prompt v2.
    """

    issue_type: SemanticIssueType = Field(
        description="Type of semantic issue detected (from Seven Deadly Sins taxonomy)"
    )
    description: str = Field(description="Concise explanation of the error in user's language")
    step_index: int | None = Field(
        default=None,
        description="Index of the affected step (0-based), null if plan-level issue",
    )
    affected_step_ids: list[str] = Field(
        default_factory=list,
        description="List of step IDs affected by this issue (for backward compatibility)",
    )
    severity: str = Field(
        default="medium",
        description="Severity: low, medium, high",
    )
    suggested_fix: str | None = Field(
        default=None,
        description="How the planner should correct this issue (actionable guidance)",
    )


class CriticalityLevel(str, Enum):
    """Risk level of the execution plan."""

    LOW = "LOW"  # Read-only, no side effects
    MEDIUM = "MEDIUM"  # State-changing but reversible
    HIGH = "HIGH"  # Irreversible actions (delete, send, pay)


class SemanticValidationOutput(BaseModel):
    """
    Structured output from semantic validation LLM.

    LangChain v1.0 pattern: Pydantic schema for with_structured_output().
    Aligned with semantic_validator_prompt v2.0 output contract.
    """

    is_valid: bool = Field(description="False if ANY blocking issue is found")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0. If < 0.8, is_valid should likely be false.",
    )
    criticality: CriticalityLevel = Field(
        default=CriticalityLevel.LOW,
        description="Risk level of the plan: LOW (read-only), MEDIUM (reversible), HIGH (irreversible)",
    )
    issues: list[SemanticIssue] = Field(
        default_factory=list,
        description="List of semantic issues found (empty if is_valid=True)",
    )
    reasoning: str = Field(description="Synthesized view of why the plan is accepted or rejected")
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Questions to ask user if intent is truly ambiguous",
    )


# ============================================================================
# Validation Result (Domain Model)
# ============================================================================


@dataclass
class SemanticValidationResult:
    """
    Result of semantic validation (domain model).

    This is what nodes receive (not the Pydantic schema).
    Aligned with "Seven Deadly Sins" taxonomy from semantic_validator_prompt v2.

    Attributes:
        is_valid: False if ANY blocking issue found
        issues: List of detected semantic issues (Seven Deadly Sins)
        confidence: Confidence score 0.0-1.0, if < 0.8 likely invalid
        criticality: Risk level (LOW/MEDIUM/HIGH)
        requires_clarification: True if user input needed
        clarification_questions: Questions to ask user
        validation_duration_seconds: Time taken for validation
        used_fallback: True if validation timed out and used fallback
        fallback_reason: Reason for fallback (for UI notification)
    """

    # Required fields (no defaults)
    is_valid: bool
    issues: list[SemanticIssue]
    confidence: float
    requires_clarification: bool
    clarification_questions: list[str]
    validation_duration_seconds: float
    # Optional fields (with defaults) - must come after required fields
    criticality: CriticalityLevel = CriticalityLevel.LOW  # Default for fallbacks (Issue #60 fix)
    used_fallback: bool = False
    fallback_reason: str | None = None  # Reason for fallback (timeout, error, etc.)
    clarification_field: str | None = (
        None  # Field for which clarification was asked (e.g., "subject")
    )


# ============================================================================
# Smart Validation Trigger Logic (v3.1 - LLM-based)
# ============================================================================
# v3.1 ARCHITECTURE CHANGE:
# - Mutation intent and cardinality risk are now detected by QueryAnalyzer LLM
# - CROSS_DOMAIN_PATTERNS removed (LLM detects secondary domains directly)
# - CARDINALITY_KEYWORDS removed (LLM sets has_cardinality_risk flag)
# - MUTATION_TOOL_PATTERNS kept only for tool name validation (internal data)
# ============================================================================

# Tool name patterns indicating mutation operations (for tool validation ONLY)
# These match against TOOL NAMES (internal data), not user queries
# Used to verify plan has correct mutation tool when user requests mutation
MUTATION_TOOL_PATTERNS = [
    "create",
    "update",
    "delete",
    "send",
    "reply",
    "forward",
    "remove",
    "add",
    "modify",
]

# ============================================================================
# FIX 2026-01-11: Tools with cross-domain capabilities
# ============================================================================
# These tools handle multiple domains intrinsically (e.g., send_email resolves
# contacts automatically via the HITL flow). A single-step plan with one of
# these tools is valid even when 2+ domains are expected.
#
# Example: "send an email to john" → domains=['emails', 'contacts']
# Plan: [send_email_draft] → Valid! The tool resolves contact via draft+HITL.
# Without this fix: semantic_validator forces re-planning → +9k tokens wasted.
# ============================================================================
CROSS_DOMAIN_CAPABLE_TOOLS = frozenset(
    [
        # Email tools that can resolve contacts via semantic_type="email_address"
        "send_email_tool",
        "send_email_draft",
        "reply_email_tool",
        "reply_email_draft",
        "forward_email_tool",
        "forward_email_draft",
        # Event tools that can resolve attendees from contacts
        "create_event_tool",
        "create_event_draft",
        "update_event_tool",
        "update_event_draft",
    ]
)


def _tool_is_mutation(tool_name: str) -> bool:
    """Check if a tool name indicates a mutation operation."""
    tool_lower = tool_name.lower()
    return any(pattern in tool_lower for pattern in MUTATION_TOOL_PATTERNS)


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

    if query_intelligence is not None:
        if isinstance(query_intelligence, dict):
            # Dict format (LangGraph serialization)
            is_mutation_intent = query_intelligence.get("is_mutation_intent", False)
            has_cardinality_risk = query_intelligence.get("has_cardinality_risk", False)
            expected_domains = query_intelligence.get("domains", [])
        else:
            # Object format (QueryIntelligence dataclass)
            is_mutation_intent = getattr(query_intelligence, "is_mutation_intent", False)
            has_cardinality_risk = getattr(query_intelligence, "has_cardinality_risk", False)
            expected_domains = getattr(query_intelligence, "domains", [])

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
        if not _tool_is_mutation(single_tool_name):
            return True, f"mutation_intent_but_no_mutation_tool:{single_tool_name}"

    # Short-circuit: single step (without cross-domain pattern) is safe
    if len(plan.steps) <= 1:
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
            mutation_at_end = _tool_is_mutation(tool_name)

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
    plan_has_mutation = any(_tool_is_mutation(step.tool_name or "") for step in plan.steps)
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


def validate_steps_references(plan: "ExecutionPlan") -> tuple[bool, str | None]:
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
# FOR_EACH Pattern Validation (plan_planner.md Section 10)
# ============================================================================


def validate_for_each_patterns(
    plan: "ExecutionPlan",
    query_intelligence: Any | None = None,
) -> tuple[bool, str | None, SemanticIssueType | None]:
    """
    Validate for_each patterns in the execution plan.

    Checks for:
    1. User said "each/every/all" but plan has no for_each step
    2. for_each_max is suspiciously low for the expected cardinality
    3. for_each reference points to valid array-producing step

    Args:
        plan: ExecutionPlan to validate
        query_intelligence: QueryIntelligence with for_each detection flags

    Returns:
        Tuple of (is_valid, error_feedback, issue_type):
            - is_valid: True if for_each patterns are valid
            - error_feedback: Correction instruction if invalid, None if valid
            - issue_type: SemanticIssueType if invalid, None if valid
    """
    # Get for_each detection from query intelligence
    for_each_detected = False
    for_each_collection_key: str | None = None
    cardinality_magnitude: int | None = None

    if query_intelligence is not None:
        if isinstance(query_intelligence, dict):
            for_each_detected = query_intelligence.get("for_each_detected", False)
            for_each_collection_key = query_intelligence.get("for_each_collection_key")
            cardinality_magnitude = query_intelligence.get("cardinality_magnitude")
        else:
            for_each_detected = getattr(query_intelligence, "for_each_detected", False)
            for_each_collection_key = getattr(query_intelligence, "for_each_collection_key", None)
            cardinality_magnitude = getattr(query_intelligence, "cardinality_magnitude", None)

    # Find for_each steps in plan
    for_each_steps = [step for step in plan.steps if step.for_each is not None]
    has_for_each_in_plan = len(for_each_steps) > 0

    # Check 1: User said "each" but plan has no for_each
    # Exception: N explicit delegate_to_sub_agent_tool steps satisfy cardinality
    # (each step delegates to a different expert — for_each iteration doesn't apply)
    if for_each_detected and not has_for_each_in_plan:
        delegate_steps = [s for s in plan.steps if s.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT]
        if len(delegate_steps) >= 2:
            logger.info(
                "for_each_satisfied_by_explicit_sub_agent_delegation",
                delegate_step_count=len(delegate_steps),
                for_each_collection_key=for_each_collection_key,
                cardinality_magnitude=cardinality_magnitude,
            )
            # Continue to Checks 2-5 (no early return)
        else:
            feedback = (
                "FOR_EACH_MISSING_CARDINALITY: User wants action for EACH "
                f"{for_each_collection_key or 'item'}, "
                "but plan has no for_each step.\n\n"
                f"Fix: Add 'for_each' field to the appropriate step:\n"
                f'  "for_each": "$steps.step_N.'
                f'{for_each_collection_key or "collection"}"\n'
                "  This will expand the step to iterate over each item."
            )
            return False, feedback, SemanticIssueType.FOR_EACH_MISSING_CARDINALITY

    # Check 2: for_each_max too low for expected cardinality
    if has_for_each_in_plan and cardinality_magnitude is not None:
        for step in for_each_steps:
            if (
                step.for_each_max < cardinality_magnitude
                and cardinality_magnitude != CARDINALITY_ALL
            ):
                feedback = (
                    f"FOR_EACH_MAX_EXCEEDED: Step {step.step_id} has for_each_max={step.for_each_max}, "
                    f"but user expects ~{cardinality_magnitude} items.\n\n"
                    f"Fix: Increase for_each_max to at least {cardinality_magnitude}:\n"
                    f'  "for_each_max": {min(cardinality_magnitude, settings.for_each_max_hard_limit)}'
                )
                return False, feedback, SemanticIssueType.FOR_EACH_MAX_EXCEEDED

    # Check 3: for_each reference points to valid step
    if has_for_each_in_plan:
        step_ids = {step.step_id for step in plan.steps}
        for step in for_each_steps:
            # Extract step_id from for_each reference
            import re

            match = re.match(r"\$steps\.(\w+)\.", step.for_each or "")
            if match:
                ref_step_id = match.group(1)
                if ref_step_id not in step_ids:
                    feedback = (
                        f"FOR_EACH_INVALID_REFERENCE: Step {step.step_id} has for_each "
                        f"pointing to non-existent step '{ref_step_id}'.\n\n"
                        f"Fix: Ensure the referenced step exists and produces an array:\n"
                        f'  "for_each": "$steps.<valid_step_id>.<array_field>"'
                    )
                    return False, feedback, SemanticIssueType.FOR_EACH_INVALID_REFERENCE

    # Check 4: for_each step parameters MUST use $item references
    # If parameters use $steps.step_X.collection[0] instead of $item, all expanded
    # steps will have the same value (the first item) instead of iterating correctly.
    if has_for_each_in_plan:
        for step in for_each_steps:
            if not step.parameters:
                continue

            # Serialize parameters to check for $item references
            params_str = json.dumps(step.parameters)

            # Check if parameters contain any reference to the for_each collection
            # but NOT using $item syntax
            has_item_ref = FOR_EACH_ITEM_REF in params_str

            # Extract the for_each reference step and collection
            # e.g., "$steps.step_1.events" → step_1, events
            for_each_match = re.match(r"\$steps\.(\w+)\.(\w+)", step.for_each or "")
            if for_each_match:
                ref_step_id = for_each_match.group(1)
                collection_key = for_each_match.group(2)

                # Check if parameters hardcode a reference to the collection with index
                # e.g., "$steps.step_1.events[0]" is wrong, should use "$item"
                # Also detect invalid placeholders like [INDEX], [i], [N], [*], etc.
                # Pattern matches: [0], [123], [INDEX], [i], [N], [*], or any bracket content
                hardcoded_pattern = rf"\$steps\.{ref_step_id}\.{collection_key}\[[^\]]+\]"
                has_hardcoded_ref = re.search(hardcoded_pattern, params_str) is not None

                if has_hardcoded_ref and not has_item_ref:
                    feedback = (
                        f"FOR_EACH_MISSING_ITEM_REF: Step {step.step_id} uses for_each but parameters "
                        f"reference '$steps.{ref_step_id}.{collection_key}[...]' instead of '$item'.\n\n"
                        f"CRITICAL: '$item' is a RESERVED KEYWORD - use it exactly as written!\n"
                        f"It is NOT a placeholder - it is the literal syntax for referencing the current item.\n\n"
                        f"WRONG patterns:\n"
                        f'  - "$steps.{ref_step_id}.{collection_key}[0].field" (hardcoded index)\n'
                        f'  - "$steps.{ref_step_id}.{collection_key}[INDEX].field" (INDEX is invalid)\n'
                        f'  - "$steps.{ref_step_id}.{collection_key}[i].field" (i is invalid)\n'
                        f'  - "$steps.{ref_step_id}.{collection_key}[*].field" (wildcard is invalid)\n\n'
                        f"CORRECT patterns:\n"
                        f'  - "$item.field" (references current item\'s field)\n'
                        f'  - "$item.nested.value" (nested field access)\n\n'
                        f"Example fix:\n"
                        f"  {{"
                        f'"trigger_datetime": "$item.start.dateTime", '
                        f'"content": "$item.summary"'
                        f"}}"
                    )
                    return False, feedback, SemanticIssueType.FOR_EACH_MISSING_ITEM_REF

    # =========================================================================
    # Check 5: STRUCTURAL DETECTION - N steps of same tool should use FOR_EACH
    # =========================================================================
    # When planner creates N separate steps of the same tool instead of using
    # for_each, detect this pattern and flag as CARDINALITY_MISMATCH.
    #
    # Example bad pattern (should trigger):
    #   step_1: get_events_tool
    #   step_2: get_route_tool (depends_on: step_1)
    #   step_3: get_route_tool (depends_on: step_1)
    #   step_4: get_route_tool (depends_on: step_1)
    #
    # This should be:
    #   step_1: get_events_tool
    #   step_2: get_route_tool with for_each="$steps.step_1.events"
    # =========================================================================
    if not has_for_each_in_plan:
        from collections import Counter

        # Count occurrences of each tool_name
        tool_counts = Counter(step.tool_name for step in plan.steps if step.tool_name)

        # Exclude delegate_to_sub_agent_tool: explicit delegation to different experts
        # is intentional and cannot be consolidated into for_each
        _TOOLS_EXEMPT_FROM_FOR_EACH_CONSOLIDATION = frozenset({TOOL_NAME_DELEGATE_SUB_AGENT})

        # Find tools with 2+ occurrences (excluding exempt tools)
        repeated_tools = [
            (tool, count)
            for tool, count in tool_counts.items()
            if count >= 2 and tool not in _TOOLS_EXEMPT_FROM_FOR_EACH_CONSOLIDATION
        ]

        for repeated_tool, count in repeated_tools:
            # Get all steps using this tool
            repeated_steps = [s for s in plan.steps if s.tool_name == repeated_tool]

            # Check if they all depend on the same parent step
            parent_dependencies = set()
            for step in repeated_steps:
                if step.depends_on:
                    for dep in step.depends_on:
                        parent_dependencies.add(dep)

            # If all repeated steps depend on a single common parent, this is
            # likely a pattern that should use FOR_EACH
            if len(parent_dependencies) == 1:
                parent_step_id = list(parent_dependencies)[0]

                # Find the parent step to get its tool_name
                parent_step = next((s for s in plan.steps if s.step_id == parent_step_id), None)

                if parent_step:
                    # Infer collection key from parent tool
                    parent_tool = parent_step.tool_name or ""
                    collection_key = "items"  # default
                    if "event" in parent_tool or "calendar" in parent_tool:
                        collection_key = "events"
                    elif "contact" in parent_tool:
                        collection_key = "contacts"
                    elif "place" in parent_tool:
                        collection_key = "places"
                    elif "email" in parent_tool:
                        collection_key = "emails"

                    feedback = (
                        f"CARDINALITY_MISMATCH: Plan has {count} separate '{repeated_tool}' steps "
                        f"that all depend on '{parent_step_id}'. This pattern should use FOR_EACH.\n\n"
                        f"Current pattern (inefficient):\n"
                        f"  - {parent_step_id}: {parent_tool}\n"
                    )
                    for step in repeated_steps:
                        feedback += f"  - {step.step_id}: {repeated_tool}\n"

                    feedback += (
                        f"\nFix: Consolidate into a single step with for_each:\n"
                        f"{{\n"
                        f'  "step_id": "step_2",\n'
                        f'  "tool_name": "{repeated_tool}",\n'
                        f'  "for_each": "$steps.{parent_step_id}.{collection_key}",\n'
                        f'  "for_each_max": {count},\n'
                        f'  "parameters": {{\n'
                        f'    "destination": "$item.location"\n'
                        f"  }}\n"
                        f"}}\n"
                    )

                    logger.info(
                        "structural_for_each_pattern_detected",
                        repeated_tool=repeated_tool,
                        count=count,
                        parent_step_id=parent_step_id,
                        parent_tool=parent_tool,
                    )

                    return False, feedback, SemanticIssueType.CARDINALITY_MISMATCH

    return True, None, None


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
            user_request: Original user message
            user_language: User language (fr, en, es)
            config: Optional RunnableConfig for LangGraph

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
            return SemanticValidationResult(
                is_valid=False,
                issues=[
                    SemanticIssue(
                        issue_type=SemanticIssueType.GHOST_DEPENDENCY,
                        description="$steps reference uses wrong result_key for step",
                        suggested_fix=refs_feedback or "Fix $steps references",
                        severity="high",
                    )
                ],
                confidence=1.0,  # Programmatic detection = 100% confident
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=time.time() - start_time,
                criticality=CriticalityLevel.HIGH,
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
            return SemanticValidationResult(
                is_valid=False,
                issues=[
                    SemanticIssue(
                        issue_type=for_each_issue,
                        description="for_each pattern issue detected",
                        suggested_fix=for_each_feedback or "Fix for_each configuration",
                        severity="high",
                    )
                ],
                confidence=1.0,  # Programmatic detection = 100% confident
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=time.time() - start_time,
                criticality=CriticalityLevel.MEDIUM,
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
            result = await asyncio.wait_for(
                self._validate_with_llm(plan, user_request, user_language, config),
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

            logger.error(
                "semantic_validation_error_fallback",
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=duration,
                exc_info=True,
            )

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
        messages = self._build_validation_prompt(plan, user_request, user_language)

        # DEBUG: Log config callbacks to verify TokenTrackingCallback is present
        if config:
            callbacks = (
                config.get("callbacks", [])
                if isinstance(config, dict)
                else getattr(config, "callbacks", [])
            )
            # Handle AsyncCallbackManager (LangChain v1.0) - not directly iterable
            # Check if callbacks has a 'handlers' attribute (CallbackManager pattern)
            if hasattr(callbacks, "handlers"):
                callback_list = callbacks.handlers
            elif isinstance(callbacks, list):
                callback_list = callbacks
            else:
                callback_list = []
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
                has_config=False,
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
            "semantic_validator_prompt",
            version=settings.semantic_validator_prompt_version,
        )

        # Build detailed plan representation for LLM
        plan_details = self._format_plan_for_validation(plan)

        # Build human message with complete plan context
        human_content = f"""## User Request
"{user_request}"

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

Respond in {user_language}."""

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
