"""Owned JSON snapshots for asynchronous, reversible collection judgments."""

from collections.abc import Mapping
from decimal import Decimal
from math import isfinite
from typing import Any

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta
from src.domains.agents.display.filter_evidence import (
    FilterEvidence,
    is_utf8_text,
    project_filter_evidence,
)

OMITTED_FIELD = "_jev_evidence_omitted"


def _reject_invalid_scalar(value: object) -> None:
    if isinstance(value, str) and not is_utf8_text(value):
        raise ValueError("Invalid source text")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("Nonfinite source evidence")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Nonfinite source evidence")


def _payload_exclusions(value: object, ancestors: set[int]) -> dict[Any, Any]:
    """Validate raw numbers before JSON can convert them; omit card subtrees first."""
    _reject_invalid_scalar(value)
    if not isinstance(value, Mapping | list | tuple | set | frozenset):
        return {}
    if id(value) in ancestors or len(ancestors) >= 32:
        # JSON serialization or the evidence projector rejects this subtree.
        return {}
    parents = ancestors | {id(value)}
    children = value.items() if isinstance(value, Mapping) else enumerate(value)
    excluded: dict[Any, Any] = {}
    for key, child in children:
        if isinstance(value, Mapping) and not isinstance(key, str):
            raise ValueError("Non-JSON source key")
        _reject_invalid_scalar(key)
        if key == FIELD_DISPLAY_ONLY:
            excluded[key] = True
        elif child_exclusions := _payload_exclusions(child, parents):
            excluded[key] = child_exclusions
    return excluded


def snapshot_collection_item(item: RegistryItem) -> RegistryItem:
    """No verdict may later be shown next to a different source revision."""
    try:
        # meta.display is intentionally unavailable to model projections and
        # may contain card-only fields; the preview reads payload evidence.
        return RegistryItem.model_validate(
            item.model_dump(
                mode="json",
                exclude={"meta": {"display"}, "payload": _payload_exclusions(item.payload, set())},
            )
        )
    except TypeError, ValueError:
        # Unsupported values are omitted, never stringified as model evidence.
        payload = {OMITTED_FIELD: True}
        if item.payload.get("_mcp_structured") is True:
            payload["_mcp_structured"] = True
        return RegistryItem(
            id=item.id,
            type=item.type,
            payload=payload,
            meta=RegistryItemMeta(source=item.meta.source, domain=item.meta.domain),
        )


def snapshot_collection_items(items: list[RegistryItem]) -> list[RegistryItem]:
    return [snapshot_collection_item(item) for item in items]


def snapshot_filter_evidence(item: RegistryItem, *, preserve_fields: bool) -> FilterEvidence:
    if item.payload.get(OMITTED_FIELD) is True:
        return FilterEvidence("[Unsupported JSON evidence omitted]", False)
    return project_filter_evidence(item.payload, preserve_fields=preserve_fields)
