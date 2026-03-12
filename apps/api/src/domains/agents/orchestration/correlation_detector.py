"""
Correlation Detector for Multi-Domain Display.

Detects correlated registry items for grouped display (e.g., Event + Route pairs).

Architecture:
    Items are correlated via the `correlated_to` field in RegistryItemMeta.
    This field is populated during FOR_EACH expansion when a child step
    (e.g., get_route) iterates over parent items (e.g., events).

    Flow:
        1. FOR_EACH expansion propagates _correlation_parent_id
        2. _execute_tool() injects correlated_to into registry item meta
        3. detect_correlations() groups items by correlation

Usage:
    >>> from src.domains.agents.orchestration.correlation_detector import detect_correlations
    >>> clusters, uncorrelated = detect_correlations(registry)
    >>> # clusters: List of CorrelatedCluster (parent + children)
    >>> # uncorrelated: Dict of domain -> items (for standard rendering)

Created: 2026-01-23
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.core.field_names import FIELD_CORRELATED_TO
from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

logger = structlog.get_logger(__name__)


@dataclass
class CorrelatedCluster:
    """
    A cluster of correlated registry items from different domains.

    Items are correlated when a child item's `correlated_to` field
    references a parent item's registry ID.

    Example: Event + Route cluster
        - parent_item: Event data (meeting at 14h)
        - child_items: [("routes", Route data)]
        - parent_domain: "events"

    Attributes:
        cluster_id: Registry ID of the parent item
        parent_item: Parent item payload (e.g., Event)
        parent_domain: Domain of parent (e.g., "events")
        child_items: List of (domain, payload) tuples for each child
    """

    cluster_id: str
    parent_item: dict[str, Any]
    parent_domain: str
    child_items: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


def detect_correlations(
    registry: dict[str, Any],
) -> tuple[list[CorrelatedCluster], dict[str, list[dict[str, Any]]]]:
    """
    Detect correlated items and group them for display.

    Groups items based on the `correlated_to` field in their metadata.
    Items without correlation are grouped by domain for standard rendering.

    Args:
        registry: Dict of registry_id -> RegistryItem (or dict representation)

    Returns:
        Tuple of:
        - clusters: List of CorrelatedCluster (parent + children grouped)
        - uncorrelated: Dict of domain -> list of payloads (for standard rendering)

    Algorithm:
        1. First pass: Identify parent IDs (items referenced by correlated_to)
        2. Second pass: Group children by their parent, collect uncorrelated
        3. Build clusters with parent + children

    Edge Cases:
        - Parent not in registry: Children rendered as uncorrelated
        - No correlated_to: Item is uncorrelated
        - Multiple children per parent: All grouped in same cluster
    """
    if not registry:
        return [], {}

    # First pass: Identify all parent IDs (items that are referenced)
    parent_ids: set[str] = set()
    for item_id, item in registry.items():
        correlated_to = _get_correlated_to(item)
        if correlated_to:
            parent_ids.add(correlated_to)
            logger.debug(
                "correlation_child_found",
                child_id=item_id,
                correlated_to=correlated_to,
            )

    # Second pass: Group items
    children_by_parent: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    uncorrelated_items: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item_id, item in registry.items():
        correlated_to = _get_correlated_to(item)
        item_type = _get_item_type(item)
        payload = _get_payload(item)
        domain = get_result_key_from_type(item_type) or "other"

        if correlated_to:
            # This is a child item - group by parent
            children_by_parent[correlated_to].append((domain, payload))
        elif item_id not in parent_ids:
            # Neither parent nor child - uncorrelated
            # Note: Don't filter on payload being truthy - empty dict {} is valid
            if payload is not None:
                uncorrelated_items[domain].append(payload)
        # else: This is a parent - will be included in cluster building

    # Build clusters
    clusters: list[CorrelatedCluster] = []
    for parent_id, children in children_by_parent.items():
        parent_item = registry.get(parent_id)
        if not parent_item:
            # Parent not in registry - treat children as uncorrelated
            # Note: Don't filter on payload being truthy - empty dict {} is valid
            for child_domain, child_payload in children:
                if child_payload is not None:
                    uncorrelated_items[child_domain].append(child_payload)
            continue

        parent_type = _get_item_type(parent_item)
        parent_payload = _get_payload(parent_item)
        parent_domain = get_result_key_from_type(parent_type) or "other"

        # Keep (domain, payload) tuples for proper rendering
        # Note: Don't filter on payload being truthy - empty dict {} is valid
        cluster = CorrelatedCluster(
            cluster_id=parent_id,
            parent_item=parent_payload or {},
            parent_domain=parent_domain,
            child_items=[
                (domain, payload or {}) for domain, payload in children if payload is not None
            ],
        )
        clusters.append(cluster)

    # Log correlation results for debugging
    if clusters:
        logger.info(
            "correlation_detection_completed",
            cluster_count=len(clusters),
            uncorrelated_domain_count=len(uncorrelated_items),
            cluster_ids=[c.cluster_id for c in clusters],
        )
    else:
        logger.debug(
            "correlation_detection_no_clusters",
            total_items=len(registry),
            uncorrelated_domain_count=len(uncorrelated_items),
        )

    return clusters, dict(uncorrelated_items)


def _get_correlated_to(item: Any) -> str | None:
    """Extract correlated_to from item (handles dict and Pydantic)."""
    if hasattr(item, "meta") and hasattr(item.meta, FIELD_CORRELATED_TO):
        return getattr(item.meta, FIELD_CORRELATED_TO)
    if isinstance(item, dict):
        meta = item.get("meta", {})
        if isinstance(meta, dict):
            return meta.get(FIELD_CORRELATED_TO)
    return None


def _get_item_type(item: Any) -> str:
    """Extract item type from item (handles dict and Pydantic)."""
    if hasattr(item, "type"):
        item_type = item.type
        return item_type.value if hasattr(item_type, "value") else str(item_type)
    if isinstance(item, dict):
        item_type = item.get("type", "")
        return item_type.value if hasattr(item_type, "value") else str(item_type)
    return ""


def _get_payload(item: Any) -> dict[str, Any] | None:
    """Extract payload from item (handles dict and Pydantic)."""
    if hasattr(item, "payload"):
        return item.payload
    if isinstance(item, dict):
        return item.get("payload")
    return None
