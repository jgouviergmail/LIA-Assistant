"""The FOR_EACH rules: when a plan must iterate, and over what.

Extracted from ``semantic_validator`` (file-size ratchet) — five checks on one
pattern, cohesive enough to read on their own: does the plan iterate when the
user asked for "each", can it iterate at all, is the cap high enough, does the
reference point somewhere real, and do the parameters actually use ``$item``.

The rules are deterministic: they read the plan and the analyzer's verdict, never
an LLM.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from src.core.config import settings
from src.core.constants import FOR_EACH_ITEM_REF, TOOL_NAME_DELEGATE_SUB_AGENT
from src.infrastructure.observability.logging import get_logger

from .plan_predicates import iterable_collections_of
from .validation_models import SemanticIssueType

if TYPE_CHECKING:
    from .plan_schemas import ExecutionPlan

logger = get_logger(__name__)

CARDINALITY_ALL = -1


def _count_for_each_demand_dropped(collection_key: str | None, plan: ExecutionPlan) -> None:
    """Record a for_each requirement dropped for lack of an iterable source.

    A rising rate points at the ANALYZER over-detecting cardinality; this only
    stops that over-detection from blocking a plan nobody could fix.

    Args:
        collection_key: The collection the analyzer believed should be iterated.
        plan: The plan whose tools produce no collection at all.
    """
    from src.infrastructure.observability.metrics_agents import (
        semantic_validation_for_each_demand_dropped,
    )

    logger.info(
        "for_each_demand_dropped_no_iterable_source",
        for_each_collection_key=collection_key,
        tools=[step.tool_name for step in plan.steps],
    )
    semantic_validation_for_each_demand_dropped.inc()


def validate_for_each_patterns(
    plan: ExecutionPlan,
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
        elif not (iterable_refs := iterable_collections_of(plan)):
            # Nothing to iterate OVER: demanding a for_each here asks the planner
            # for `$steps.step_N.<collection>` when no step declares a collection
            # at all. No plan can satisfy it, so the verdict never converges —
            # prod dev 2026-08-02: "the 3 first results" read as "for EACH
            # browsers", 16 planning cycles and a clarification loop the user
            # could not escape (their answer cannot change what the ANALYZER
            # decided about the original message).
            # Deliberately narrow: it takes PROOF that no collection exists, so a
            # genuinely missing for_each over `contacts[]` is still caught.
            _count_for_each_demand_dropped(for_each_collection_key, plan)
            # Continue to Checks 2-5 (no early return)
        else:
            # The suggested reference names a collection the plan REALLY
            # produces (manifest-backed), never the context key the analyzer
            # guessed: `web_searchs` IS a declared context type, but the tool
            # returns `results` — pointing at the former sends the planner
            # after a reference that can never resolve (ADR-184: what a
            # validator demands, its producer must be able to produce).
            feedback = (
                "FOR_EACH_MISSING_CARDINALITY: User wants action for EACH "
                f"{for_each_collection_key or 'item'}, "
                "but plan has no for_each step.\n\n"
                f"Fix: Add 'for_each' field to the appropriate step:\n"
                f'  "for_each": "{iterable_refs[0]}"\n'
                "  This will expand the step to iterate over each item.\n"
                f"  Collections this plan produces: {', '.join(iterable_refs)}"
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
