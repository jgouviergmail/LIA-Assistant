"""Domain models of semantic plan validation (enums + schemas + result).

Extracted from ``semantic_validator.py`` (file-size ratchet: the validator
logic grew with the deterministic pre-LLM guards while these models are pure
data contracts with no dependency on it). ``semantic_validator`` re-exports
every name, so historical import sites keep working unchanged.

Aligned with the "Seven Deadly Sins" taxonomy from semantic_validator_prompt v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


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
    user_facing: bool = Field(
        default=True,
        description=(
            "Whether `description` may be shown to the user as-is. True for the "
            "LLM path, which honours the 'in user's language' contract above and "
            "says something specific ('La date de début est incorrecte'). The "
            "deterministic pre-LLM rules set it to False: their descriptions are "
            "English technical literals meant for the trace and the replan "
            "prompt, and showing one delivered 'for_each pattern issue detected' "
            "to a French account (prod 2026-08-02). A False description is "
            "replaced by the localized question for its issue type."
        ),
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
