"""Check explicit requested results against canonical tool observations.

Opaque results stay unknown. A pending draft is not an executed action. An empty
collection can satisfy a zero-minimum request, and absence of a cursor never
proves that retrieval was complete.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from hashlib import sha256
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, MCP_TOOL_NAME_PREFIX
from src.domains.agents.analysis.requested_outcomes import (
    GoalFieldExpectation,
    GoalRequirement,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.registry.catalogue import get_tool_category, is_read_only_tool
from src.domains.agents.semantic.manifest_semantics import available_manifest

OutcomeStatus = Literal[
    "satisfied", "missing", "failed", "partial", "pending_confirmation", "unknown"
]


class OutcomeEvidence(BaseModel):
    """A serializable observation captured before result projection/truncation."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    domain: str
    kind: Literal["read", "action", "unknown"]
    operation: str | None = None
    success: bool | None = None
    pending_confirmation: bool = False
    complete: bool | None = None
    arguments: dict[str, object]
    data: dict[str, object]
    requirement_statuses: dict[str, OutcomeStatus] | None = None
    observed_counts: dict[str, int] | None = None


class GoalCoverage(BaseModel):
    """A factual coverage verdict, separate from the model's final prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement: GoalRequirement
    status: OutcomeStatus
    tool_names: tuple[str, ...] = ()


_GOAL_GAP_STATUSES: frozenset[OutcomeStatus] = frozenset({"missing", "failed", "partial"})


def coverage_has_gap(coverage: GoalCoverage) -> bool:
    """Read the closed requested-goal vocabulary independently of AgentResultStatus."""
    return coverage.status in _GOAL_GAP_STATUSES


def _object(value: object) -> dict[str, object] | None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError, TypeError:
            return None
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return dict(value)
    return None


def _completeness(data: Mapping[str, object]) -> bool | None:
    if data.get("partial") is True or data.get("truncated") is True:
        return False
    if any(data.get(key) for key in ("next_page_token", "nextPageToken", "next_cursor")):
        return False
    if data.get("has_more") is True:
        return False
    for key in ("retrieval_complete", "complete"):
        if isinstance(data.get(key), bool):
            return data[key] is True
    return None


def observe_requested_outcome(
    tool_name: str,
    arguments: Mapping[str, object],
    raw_result: object,
    *,
    requirements: Sequence[GoalRequirement] | None = None,
    timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> dict[str, object] | None:
    """Capture an available tool's canonical output, never an LLM claim."""
    manifest = available_manifest(tool_name)
    raw = _object(raw_result)
    if manifest is None or raw is None:
        return None
    selected = tuple(
        goal
        for goal in (requirements or ())
        if goal.domain == manifest.agent.removesuffix("_agent")
    )
    if requirements is not None and not selected:
        return None
    data = _canonical_data(raw)
    success = raw.get("success")
    read_only = is_read_only_tool(manifest)
    evidence = OutcomeEvidence(
        tool_name=tool_name,
        domain=manifest.agent.removesuffix("_agent"),
        kind=_observed_kind(manifest.delegates_execution, read_only),
        operation=(
            None
            if read_only or tool_name.startswith(MCP_TOOL_NAME_PREFIX)
            else get_tool_category(manifest)
        ),
        success=success if isinstance(success, bool) else None,
        pending_confirmation=_pending_confirmation(
            read_only, manifest.mutation_policy, data, tool_name
        ),
        complete=_merged_completeness(data, _object(raw.get("metadata"))),
        arguments=dict(arguments),
        data=data,
    )
    if requirements is not None:
        evidence = _compact_evidence(evidence, selected, timezone)
    serialized: dict[str, object] = evidence.model_dump(mode="json")
    return serialized


def _canonical_data(raw: dict[str, object]) -> dict[str, object]:
    data = _object(raw.get("structured_data"))
    if data is not None:
        return data
    data = _object(raw.get("data"))
    return data if data is not None else raw


def _observed_kind(
    delegates_execution: bool, read_only: bool
) -> Literal["read", "action", "unknown"]:
    if delegates_execution:
        return "unknown"
    return "read" if read_only else "action"


def _pending_confirmation(
    read_only: bool, policy: str | None, data: Mapping[str, object], tool_name: str
) -> bool:
    if read_only:
        return False
    if data.get("draft_id") or data.get("drafts") or data.get("draft"):
        return True
    if policy != "draft":
        return False
    if APPLICATION_OPERATIONS.get_by_tool_name(tool_name) is None:
        return True
    result = _object(data.get("application_result"))
    if result is None or result.get("committed") is not True or result.get("success") is not True:
        return True
    try:
        outcome = ApplicationExecutionOutcome.model_validate(result)
    except ValidationError:
        return True
    return not outcome.success


def _field(item: Mapping[str, object], path: str) -> object:
    current: object = item
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            return None
        current = current[component]
    return current


def _date_of(value: object, timezone: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is not None:
            instant = instant.astimezone(ZoneInfo(timezone))
        return instant.date().isoformat()
    except ValueError, KeyError:
        return None


def _matches(
    item: Mapping[str, object], expectation: GoalFieldExpectation, timezone: str
) -> bool | None:
    actual = _field(item, expectation.field)
    if actual is None:
        return None
    if expectation.operator == "on_date":
        actual = _date_of(actual, expectation.reference_timezone or timezone)
        return None if actual is None else actual == expectation.expected_value
    if isinstance(actual, (str, int, float, bool)):
        return str(actual) == expectation.expected_value
    return None


def _items(evidence: OutcomeEvidence, goal: GoalRequirement) -> list[dict[str, object]] | None:
    value = _field(evidence.data, goal.collection_key) if goal.collection_key else evidence.data
    if isinstance(value, list):
        items = [_object(item) for item in value]
        return (
            None
            if any(item is None for item in items)
            else [item for item in items if item is not None]
        )
    item = _object(value)
    return [item] if item is not None else None


def _coverage(goal: GoalRequirement, evidence: OutcomeEvidence, timezone: str) -> OutcomeStatus:
    if evidence.kind == "unknown":
        return "unknown"
    if evidence.requirement_statuses is not None:
        return evidence.requirement_statuses.get(_requirement_key(goal), "unknown")
    if evidence.success is False:
        return "failed"
    if evidence.pending_confirmation:
        return "pending_confirmation"
    if goal.kind == "action" and evidence.operation is None:
        return "unknown"
    items = _items(evidence, goal)
    if items is None:
        return "unknown"
    field_status = _field_coverage(goal, items, timezone)
    if field_status is not None:
        return field_status
    if goal.requires_complete and evidence.complete is not True:
        return "unknown" if evidence.complete is None else "partial"
    if goal.kind == "action" and not _action_proven(goal, evidence):
        return "unknown"
    return "satisfied"


def _field_coverage(
    goal: GoalRequirement, items: list[dict[str, object]], timezone: str
) -> OutcomeStatus | None:
    matched, unknown = _matching_counts(goal, items, timezone)
    minimum = goal.min_count
    if minimum is None:
        minimum = 1 if goal.expected_fields or goal.kind == "action" else 0
    if matched < minimum:
        return "unknown" if unknown else "missing"
    return None


def _action_proven(goal: GoalRequirement, evidence: OutcomeEvidence) -> bool:
    return (
        evidence.success is True
        and goal.operation is not None
        and evidence.operation == goal.operation
        and bool(goal.expected_fields)
    )


def _merged_completeness(
    data: Mapping[str, object], metadata: Mapping[str, object] | None
) -> bool | None:
    markers = (_completeness(data), _completeness(metadata or {}))
    if False in markers:
        return False
    return True if True in markers else None


def requested_outcome_coverage(
    requirements: Sequence[GoalRequirement], observations: object, *, timezone: str
) -> tuple[GoalCoverage, ...]:
    """All constraints must match the same item; later recovery can replace failure."""
    evidence: list[OutcomeEvidence] = []
    if isinstance(observations, list):
        for observation in observations:
            try:
                evidence.append(OutcomeEvidence.model_validate(observation))
            except ValidationError:
                continue
    coverage: list[GoalCoverage] = []
    for goal in requirements:
        relevant = [item for item in evidence if _relevant(goal, item)]
        statuses = [_coverage(goal, item, timezone) for item in relevant]
        status = _combined_status(goal, relevant, statuses, timezone)
        coverage.append(
            GoalCoverage(
                requirement=goal,
                status=status,
                tool_names=tuple(item.tool_name for item in relevant),
            )
        )
    return tuple(coverage)


def _relevant(goal: GoalRequirement, evidence: OutcomeEvidence) -> bool:
    return (
        evidence.domain == goal.domain
        and (evidence.kind == "unknown" or evidence.kind == goal.kind)
        and (
            goal.kind != "action"
            or goal.operation is None
            or evidence.operation is None
            or evidence.operation == goal.operation
        )
    )


def _requirement_key(goal: GoalRequirement) -> str:
    return sha256(goal.model_dump_json().encode("utf-8")).hexdigest()


def _compact_evidence(
    evidence: OutcomeEvidence, goals: Sequence[GoalRequirement], timezone: str
) -> OutcomeEvidence:
    """Keep exact verdicts/counts for these immutable constraints, without duplicating payloads."""
    statuses = {_requirement_key(goal): _coverage(goal, evidence, timezone) for goal in goals}
    counts = {
        _requirement_key(goal): _matching_counts(goal, _items(evidence, goal) or [], timezone)[0]
        for goal in goals
    }
    compact: OutcomeEvidence = evidence.model_copy(
        update={
            "arguments": {},
            "data": {},
            "requirement_statuses": statuses,
            "observed_counts": counts,
        }
    )
    return compact


def _matching_counts(
    goal: GoalRequirement, items: list[dict[str, object]], timezone: str
) -> tuple[int, bool]:
    judgments = [
        tuple(_matches(item, field, timezone) for field in goal.expected_fields) for item in items
    ]
    return (
        sum(all(match is True for match in row) for row in judgments),
        any(any(match is None for match in row) for row in judgments),
    )


def _combined_status(
    goal: GoalRequirement,
    evidence: list[OutcomeEvidence],
    statuses: list[OutcomeStatus],
    timezone: str,
) -> OutcomeStatus:
    if "satisfied" in statuses:
        return "satisfied"
    if (
        goal.kind == "read"
        and len(statuses) > 1
        and all(status == "missing" for status in statuses)
    ):
        # Without a verified page chain/entity identity, neither completeness nor
        # a missing count is proved by these independent contributions.
        count = sum(_observed_count(goal, item, timezone) for item in evidence)
        if goal.min_count is not None and count >= goal.min_count:
            return "unknown"
    return statuses[-1] if statuses else "missing"


def _observed_count(goal: GoalRequirement, evidence: OutcomeEvidence, timezone: str) -> int:
    if evidence.observed_counts is not None:
        return evidence.observed_counts.get(_requirement_key(goal), 0)
    return _matching_counts(goal, _items(evidence, goal) or [], timezone)[0]
