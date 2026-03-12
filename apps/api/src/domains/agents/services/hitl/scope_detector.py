"""
Scope Detector - Identifies dangerous operation scopes for enhanced HITL.

This module detects when an operation has dangerous scope that requires
enhanced confirmation via DESTRUCTIVE_CONFIRM HITL type.

Detection Criteria:
    - Bulk operations (3+ items)
    - Destructive operations (delete, remove, clear)
    - Broad scope indicators ("all", "every", "entire")
    - Time range deletions ("all emails from last week")

Integration Points:
    - Planner node: Before creating execution plan
    - Tool node: Before executing destructive tools
    - Draft service: Before bulk draft operations

Usage:
    >>> from src.domains.agents.services.hitl.scope_detector import (
    ...     detect_dangerous_scope,
    ...     DangerousScope,
    ... )
    >>> # Use with ORIGINAL user query (before semantic pivot) for pattern matching
    >>> scope = detect_dangerous_scope(
    ...     operation_type="delete_emails",
    ...     query="delete all emails from Jean",  # english_query from semantic pivot
    ...     affected_count=15,
    ...     language="en",  # Use "en" when query is from semantic pivot
    ... )
    >>> if scope.requires_confirmation:
    ...     # Trigger DESTRUCTIVE_CONFIRM HITL
    ...     ...

References:
    - destructive_confirm.py: HITL interaction implementation
    - protocols.py: HitlInteractionType.DESTRUCTIVE_CONFIRM
    - schemas.py: DestructiveConfirmContext

Created: 2026-01-11
Phase 3: HITL Safety Enrichment
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from src.core.config import settings
from src.core.constants import (
    SCOPE_BROAD_PATTERNS,
    SCOPE_BULK_THRESHOLD,
    SCOPE_CRITICAL_THRESHOLD,
    SCOPE_DESTRUCTIVE_PATTERNS,
    SCOPE_HIGH_RISK_THRESHOLD,
    SCOPE_OPERATION_TYPES,
)

# NOTE: FOR_EACH thresholds are accessed via settings.for_each_*_threshold
# for full configurability via .env


class ScopeRisk(str, Enum):
    """Risk level of operation scope."""

    LOW = "low"  # Single item, reversible
    MEDIUM = "medium"  # Few items or semi-destructive
    HIGH = "high"  # Many items or destructive
    CRITICAL = "critical"  # Bulk destructive (e.g., "delete all")


@dataclass
class DangerousScope:
    """
    Result of dangerous scope detection.

    Attributes:
        requires_confirmation: Whether enhanced confirmation is needed
        risk_level: Risk classification
        operation_type: Normalized operation type
        affected_count: Estimated affected items
        reason: Human-readable reason for classification
        indicators: List of detected danger indicators
    """

    requires_confirmation: bool
    risk_level: ScopeRisk
    operation_type: str
    affected_count: int = 1
    reason: str = ""
    indicators: list[str] = field(default_factory=list)


# ============================================================================
# PATTERNS (English Only - Semantic Pivot)
# ============================================================================
# All patterns use English because queries come from semantic pivot.
# Centralized in core.constants for DRY. Compiled here for performance.
# Multilingual patterns removed 2026-01.
# ============================================================================

# Pre-compiled patterns for performance (compiled at module load time)
BROAD_SCOPE_PATTERNS_COMPILED: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE) for pattern in SCOPE_BROAD_PATTERNS
]

DESTRUCTIVE_KEYWORDS_COMPILED: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE) for pattern in SCOPE_DESTRUCTIVE_PATTERNS
]

# Operation type mapping (from constants, pre-compiled for word boundary matching)
OPERATION_TYPES: dict[str, str] = SCOPE_OPERATION_TYPES
_OPERATION_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    keyword: re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE) for keyword in OPERATION_TYPES
}

# Thresholds imported from core.constants (SCOPE_BULK_THRESHOLD, etc.)
# FOR_EACH thresholds are in settings (for_each_*_threshold) - configurable via .env

# Mutation tool name patterns for for_each scope detection
# Frozenset for O(1) lookup performance
_MUTATION_SUBSTRINGS: frozenset[str] = frozenset(
    {"send", "create", "update", "delete", "remove", "add", "modify"}
)


def detect_dangerous_scope(
    operation_type: str | None = None,
    query: str | None = None,
    affected_count: int = 1,
    language: str = "en",
) -> DangerousScope:
    """
    Detect if an operation has dangerous scope requiring enhanced confirmation.

    IMPORTANT: Query should be english_query from semantic pivot. All patterns
    are English-only. The `language` parameter is kept for backward compatibility
    but is ignored (patterns are always English).

    Args:
        operation_type: Type of operation (e.g., "delete_emails")
        query: Query for pattern analysis (use english_query from semantic pivot)
        affected_count: Known number of affected items
        language: Ignored (kept for backward compat). All patterns are English.

    Returns:
        DangerousScope with classification and confirmation requirement
    """
    indicators: list[str] = []
    risk_level = ScopeRisk.LOW
    requires_confirmation = False
    reason = ""

    # Normalize operation type from query if not provided
    if not operation_type and query:
        operation_type = _extract_operation_type(query)

    operation_type = operation_type or "unknown"

    # Check for broad scope patterns in query (English only - semantic pivot)
    if query:
        query_lower = query.lower()

        for compiled_pattern in BROAD_SCOPE_PATTERNS_COMPILED:
            if compiled_pattern.search(query_lower):
                indicators.append(f"broad_scope:{compiled_pattern.pattern}")
                risk_level = ScopeRisk.HIGH

        # Check for destructive keywords (English only - semantic pivot)
        for compiled_pattern in DESTRUCTIVE_KEYWORDS_COMPILED:
            if compiled_pattern.search(query_lower):
                indicators.append(f"destructive:{compiled_pattern.pattern}")

    # Evaluate by affected count (thresholds from core.constants)
    if affected_count >= SCOPE_CRITICAL_THRESHOLD:
        risk_level = ScopeRisk.CRITICAL
        indicators.append(f"count:{affected_count}>=critical")
    elif affected_count >= SCOPE_HIGH_RISK_THRESHOLD:
        if risk_level != ScopeRisk.CRITICAL:
            risk_level = ScopeRisk.HIGH
        indicators.append(f"count:{affected_count}>=high")
    elif affected_count >= SCOPE_BULK_THRESHOLD:
        if risk_level == ScopeRisk.LOW:
            risk_level = ScopeRisk.MEDIUM
        indicators.append(f"count:{affected_count}>=bulk")

    # Determine if confirmation is required
    if risk_level in (ScopeRisk.HIGH, ScopeRisk.CRITICAL):
        requires_confirmation = True
        reason = _build_reason(risk_level, affected_count, indicators)
    elif risk_level == ScopeRisk.MEDIUM and operation_type.startswith("delete_"):
        # Medium risk + destructive = requires confirmation
        requires_confirmation = True
        reason = _build_reason(risk_level, affected_count, indicators)

    return DangerousScope(
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        operation_type=operation_type,
        affected_count=affected_count,
        reason=reason,
        indicators=indicators,
    )


def _extract_operation_type(query: str) -> str:
    """
    Extract operation type from query text using word boundary matching.

    Uses pre-compiled regex patterns with word boundaries to prevent
    false positives (e.g., "emails" in "not_emails").

    IMPORTANT: Query should be english_query from semantic pivot.
    All patterns are English-only (centralized in core.constants).

    Args:
        query: Query text (english_query from semantic pivot)

    Returns:
        Normalized operation type or "unknown"
    """
    for keyword, compiled_pattern in _OPERATION_TYPE_PATTERNS.items():
        if compiled_pattern.search(query):
            return OPERATION_TYPES[keyword]

    return "unknown"


def _build_reason(
    risk_level: ScopeRisk,
    affected_count: int,
    indicators: list[str],  # noqa: ARG001 - kept for future extension
) -> str:
    """
    Build human-readable reason for confirmation requirement (internal logging).

    NOTE: This is for internal logging/debugging only. User-facing messages
    use HitlMessages.get_destructive_operation_description() from i18n_hitl.py
    which provides proper i18n support for all 6 languages.

    Args:
        risk_level: Risk classification
        affected_count: Number of affected items
        indicators: Detected indicators (reserved for future use)

    Returns:
        English reason string for logging
    """
    reasons = {
        ScopeRisk.CRITICAL: f"Critical operation affecting {affected_count} items",
        ScopeRisk.HIGH: f"High-risk operation ({affected_count} items)",
        ScopeRisk.MEDIUM: f"Bulk operation ({affected_count} items)",
    }

    return reasons.get(risk_level, f"Operation affects {affected_count} items")


def should_escalate_to_destructive_confirm(
    tool_name: str,
    tool_args: dict,  # noqa: ARG001 - kept for interface compatibility
    result_count: int | None = None,
    original_query: str | None = None,
) -> DangerousScope | None:
    """
    Check if a tool execution should escalate to DESTRUCTIVE_CONFIRM.

    Called by tool node after initial query to assess scope.

    IMPORTANT: Do NOT use tool_args["query"] for pattern matching - it's transformed
    (e.g., Gmail syntax). Use original_query (english_query from semantic pivot) instead.

    Args:
        tool_name: Name of the tool being executed
        tool_args: Tool arguments (unused - transformed query not suitable for patterns)
        result_count: Number of items that would be affected (if known)
        original_query: english_query from semantic pivot for pattern matching

    Returns:
        DangerousScope if escalation needed, None otherwise
    """
    # Map tool names to operation types
    tool_operation_map = {
        "delete_email": "delete_emails",
        "delete_emails": "delete_emails",
        "delete_contact": "delete_contacts",
        "delete_contacts": "delete_contacts",
        "delete_event": "delete_events",
        "delete_events": "delete_events",
        "delete_task": "delete_tasks",
        "delete_tasks": "delete_tasks",
        "delete_file": "delete_files",
        "delete_files": "delete_files",
    }

    operation_type = tool_operation_map.get(tool_name)
    if not operation_type:
        return None

    affected_count = result_count or 1

    scope = detect_dangerous_scope(
        operation_type=operation_type,
        query=original_query,
        affected_count=affected_count,
    )

    return scope if scope.requires_confirmation else None


# ============================================================================
# FOR_EACH Scope Detection (plan_planner.md Section 12)
# ============================================================================


@dataclass
class ForEachScope:
    """
    Result of for_each scope detection.

    Attributes:
        requires_approval: Whether HITL approval is needed
        risk_level: Risk classification
        iteration_count: Number of iterations planned
        is_mutation: Whether the iterated action is a mutation
        tool_name: Name of the tool being iterated
        reason: Human-readable reason for classification
    """

    requires_approval: bool
    risk_level: ScopeRisk
    iteration_count: int
    is_mutation: bool
    tool_name: str
    reason: str = ""


def detect_for_each_scope(
    iteration_count: int,
    tool_name: str,
    is_mutation: bool = False,
    for_each_max: int = 10,
) -> ForEachScope:
    """
    Detect if a for_each operation requires HITL approval.

    Decision matrix:
        - Mutation + 3+ iterations → Always requires approval (HIGH risk)
        - Non-mutation + 10+ iterations → Requires approval (MEDIUM risk)
        - Non-mutation + 5+ iterations → Advisory warning (LOW risk)
        - Otherwise → No approval needed

    Args:
        iteration_count: Number of items to iterate over
        tool_name: Name of the tool being called for each item
        is_mutation: True if tool is a mutation (send, create, update, delete)
        for_each_max: Current for_each_max limit from step config

    Returns:
        ForEachScope with classification and approval requirement

    Example:
        >>> scope = detect_for_each_scope(
        ...     iteration_count=15,
        ...     tool_name="send_email_tool",
        ...     is_mutation=True,
        ... )
        >>> scope.requires_approval  # True
        >>> scope.risk_level  # ScopeRisk.HIGH
    """
    # Determine if this is a mutation tool (using pre-defined patterns)
    if not is_mutation:
        tool_name_lower = tool_name.lower()
        is_mutation = any(pattern in tool_name_lower for pattern in _MUTATION_SUBSTRINGS)

    # Apply thresholds
    risk_level = ScopeRisk.LOW
    requires_approval = False
    reason = ""

    if is_mutation:
        # Mutations are always more risky
        # Threshold from settings (default=1, configurable via FOR_EACH_MUTATION_THRESHOLD env var)
        mutation_threshold = settings.for_each_mutation_threshold
        if iteration_count >= mutation_threshold:
            risk_level = ScopeRisk.HIGH
            requires_approval = True
            reason = f"Mutation operation ({tool_name}) will execute {iteration_count} times"
        elif iteration_count >= 2:
            risk_level = ScopeRisk.MEDIUM
            reason = f"Multiple mutations planned ({iteration_count} items)"
    else:
        # Non-mutation (read-only) operations
        # Use settings for configurable thresholds (from .env)
        if iteration_count >= settings.for_each_warning_threshold:
            risk_level = ScopeRisk.MEDIUM
            requires_approval = True
            reason = f"Large iteration count ({iteration_count} items)"
        elif iteration_count >= settings.for_each_approval_threshold:
            risk_level = ScopeRisk.LOW
            reason = f"Moderate iteration count ({iteration_count} items)"

    # Check if iteration_count exceeds for_each_max (always flag this)
    if iteration_count > for_each_max:
        requires_approval = True
        if risk_level == ScopeRisk.LOW:
            risk_level = ScopeRisk.MEDIUM
        reason = f"Iteration count ({iteration_count}) exceeds limit ({for_each_max})"

    return ForEachScope(
        requires_approval=requires_approval,
        risk_level=risk_level,
        iteration_count=iteration_count,
        is_mutation=is_mutation,
        tool_name=tool_name,
        reason=reason,
    )
