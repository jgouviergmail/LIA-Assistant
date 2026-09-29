"""Faithful semantic evidence for result filtering, separate from voice summaries.

A display summary can shorten a list or replace a nested object with its name.
A filter cannot: the omitted attendee, a false flag or a short email body may
be the very evidence it needs. Preserve those fields and their relationships;
exclude the same transport metadata as the display serializer. Existing content
length limits remain explicit, so an incomplete field cannot look complete.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from src.domains.agents.display.llm_serializer import CONTENT_MAX_LENGTH, SKIP_FIELDS, SKIP_PATTERNS

# Builder aliases for provider identifiers; filtering must return registry ids.
_BUILDER_IDS = frozenset({"task_id", "tasklist_id", "calendar_id"})


@dataclass(frozen=True)
class FilterEvidence:
    """Text plus machine-readable omission information, separate from source prose."""

    text: str
    complete: bool


def project_filter_evidence(
    payload: Mapping[str, object], *, preserve_fields: bool = False
) -> FilterEvidence:
    omissions: list[bool] = []
    text = _render(payload, set(), omissions, preserve_fields)
    return FilterEvidence(text, not omissions)


def payload_to_filter_text(payload: Mapping[str, object]) -> str:
    """Render user-facing evidence without the display-name/short-content heuristics."""
    return project_filter_evidence(payload).text


def _render(
    value: object, ancestors: set[int], omissions: list[bool], preserve_fields: bool
) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        if len(value) > CONTENT_MAX_LENGTH:
            omissions.append(True)
            return (
                value[:CONTENT_MAX_LENGTH]
                + f" [truncated: {len(value) - CONTENT_MAX_LENGTH} characters omitted]"
            )
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    if not isinstance(value, Mapping | list | tuple):
        omissions.append(True)
        return ""
    if id(value) in ancestors:
        omissions.append(True)
        return "[cyclic value omitted]"
    if len(ancestors) >= 32:
        omissions.append(True)
        return "[depth limit: nested evidence omitted]"
    parents = ancestors | {id(value)}
    if isinstance(value, Mapping):
        return _render_fields(value, parents, omissions, preserve_fields)
    return (
        "["
        + "; ".join(
            "{" + _render(child, parents, omissions, preserve_fields) + "}" for child in value
        )
        + "]"
    )


def _render_fields(
    value: Mapping[object, object], parents: set[int], omissions: list[bool], preserve_fields: bool
) -> str:
    """Keep field names attached to their evidence, excluding transport metadata."""
    fields = []
    for key, child in value.items():
        if not isinstance(key, str):
            omissions.append(True)
            continue
        if not preserve_fields and _is_transport_field(key):
            continue
        rendered = _render(child, parents, omissions, preserve_fields)
        if rendered:
            fields.append(f"{key}: {rendered}")
    return " | ".join(fields)


def _is_transport_field(key: str) -> bool:
    normalized = key.lower()
    return normalized in SKIP_FIELDS | _BUILDER_IDS or normalized.startswith(SKIP_PATTERNS)
