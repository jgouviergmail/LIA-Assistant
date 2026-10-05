"""Faithful semantic evidence for result filtering, separate from voice summaries.

A display summary can shorten a list or replace a nested object with its name.
A filter cannot: the omitted attendee, a false flag or a short email body may
be the very evidence it needs. Preserve those fields and their relationships;
exclude provider identifiers and private transport metadata. Mail labels are
semantic evidence even though the voice serializer omits them. Existing content
length limits remain explicit, so an incomplete field cannot look complete.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from pydantic import JsonValue

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.display.llm_serializer import CONTENT_MAX_LENGTH, SKIP_FIELDS, SKIP_PATTERNS

# Builder aliases for provider identifiers; filtering must return registry ids.
_BUILDER_IDS = frozenset({"task_id", "tasklist_id", "calendar_id"})
_SEMANTIC_FIELDS = frozenset({"labelids", "label_ids"})
_TRANSPORT_FIELDS = SKIP_FIELDS - _SEMANTIC_FIELDS


@dataclass(frozen=True)
class FilterEvidence:
    """Text plus machine-readable omission information, separate from source prose."""

    text: str
    complete: bool
    data: JsonValue = None


def project_filter_evidence(
    payload: Mapping[str, object], *, preserve_fields: bool = False
) -> FilterEvidence:
    omissions: list[bool] = []
    data = _project(payload, set(), omissions, preserve_fields)
    return FilterEvidence(_text(data), not omissions, data)


def payload_to_filter_text(payload: Mapping[str, object]) -> str:
    """Render user-facing evidence without the display-name/short-content heuristics."""
    return project_filter_evidence(payload).text


def is_utf8_text(value: str) -> bool:
    """Reject invalid source text rather than silently repairing its evidence."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _project(
    value: object, ancestors: set[int], omissions: list[bool], preserve_fields: bool
) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) > CONTENT_MAX_LENGTH:
            omissions.append(True)
            value = (
                value[:CONTENT_MAX_LENGTH]
                + f" [truncated: {len(value) - CONTENT_MAX_LENGTH} characters omitted]"
            )
        if not is_utf8_text(value):
            omissions.append(True)
            return None
        return value
    if isinstance(value, bool | int):
        try:
            str(value)
        except ValueError:
            omissions.append(True)
            return None
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    if not isinstance(value, Mapping | list | tuple):
        omissions.append(True)
        return None
    if id(value) in ancestors:
        omissions.append(True)
        return "[cyclic value omitted]"
    if len(ancestors) >= 32:
        omissions.append(True)
        return "[depth limit: nested evidence omitted]"
    parents = ancestors | {id(value)}
    if isinstance(value, Mapping):
        return _project_fields(value, parents, omissions, preserve_fields)
    return [_project(child, parents, omissions, preserve_fields) for child in value]


def _project_fields(
    value: Mapping[object, object], parents: set[int], omissions: list[bool], preserve_fields: bool
) -> dict[str, JsonValue]:
    """Keep field names attached to their evidence, excluding transport metadata."""
    fields = {}
    for key, child in value.items():
        if not isinstance(key, str) or not is_utf8_text(key):
            omissions.append(True)
            continue
        if key == FIELD_DISPLAY_ONLY or (not preserve_fields and _is_transport_field(key)):
            continue
        fields[key] = _project(child, parents, omissions, preserve_fields)
    return fields


def _text(value: JsonValue) -> str:
    """Retain the existing text seam; native decisions receive the typed tree."""
    if value is None:
        return "null"
    if isinstance(value, dict):
        return " | ".join(f"{key}: {_text(child)}" for key, child in value.items())
    if isinstance(value, list):
        return "[" + "; ".join("{" + _text(child) + "}" for child in value) + "]"
    return str(value)


def _is_transport_field(key: str) -> bool:
    normalized = key.lower()
    return normalized in _TRANSPORT_FIELDS | _BUILDER_IDS or normalized.startswith(SKIP_PATTERNS)
