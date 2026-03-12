"""
Provider resolver for functional categories.

Resolves the active connector type for a functional category (email, calendar, contacts).
Uses the existing Redis-cached get_user_connectors() to avoid extra DB queries.

Created: 2026-03-10
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.domains.connectors.models import (
    CATEGORY_DISPLAY_NAMES,
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    ConnectorStatus,
    ConnectorType,
)

if TYPE_CHECKING:
    from src.domains.agents.dependencies import ToolDependencies

logger = structlog.get_logger(__name__)

# Legacy connector type aliases.
# GMAIL (deprecated) is functionally equivalent to GOOGLE_GMAIL.
# This map lets the resolver treat legacy types as their canonical counterparts
# without polluting CONNECTOR_FUNCTIONAL_CATEGORIES (which enforces 2-member categories).
_LEGACY_CONNECTOR_ALIASES: dict[ConnectorType, ConnectorType] = {
    ConnectorType.GMAIL: ConnectorType.GOOGLE_GMAIL,
}


async def resolve_active_connector(
    user_id: UUID,
    functional_category: str,
    connector_service: Any,
) -> ConnectorType | None:
    """
    Resolve the active connector type for a functional category.

    Uses get_user_connectors() which is already cached in Redis (TTL 5min).
    No additional DB query.

    Args:
        user_id: User UUID.
        functional_category: Category name ("email", "calendar", "contacts").
        connector_service: ConnectorService instance.

    Returns:
        The active ConnectorType for this category, or None if none active.
    """
    category_types = CONNECTOR_FUNCTIONAL_CATEGORIES.get(functional_category)
    if category_types is None:
        logger.warning(
            "provider_resolver_unknown_category",
            category=functional_category,
        )
        return None

    # get_user_connectors() returns ConnectorListResponse (cached in Redis TTL 300s)
    response = await connector_service.get_user_connectors(user_id)

    active_connectors = []
    for connector in response.connectors:
        ct = connector.connector_type
        # Resolve legacy aliases (e.g., GMAIL → GOOGLE_GMAIL)
        canonical_ct = _LEGACY_CONNECTOR_ALIASES.get(ct, ct)
        if canonical_ct in category_types and connector.status == ConnectorStatus.ACTIVE:
            active_connectors.append(connector)

    if not active_connectors:
        return None

    if len(active_connectors) == 1:
        return ConnectorType(active_connectors[0].connector_type)

    # Dual-active conflict (should not happen, but handle gracefully)
    # Choose the most recently updated one
    logger.warning(
        "provider_resolver_dual_active",
        user_id=str(user_id),
        category=functional_category,
        active_types=[c.connector_type.value for c in active_connectors],
    )
    active_connectors.sort(key=lambda c: c.updated_at, reverse=True)
    return ConnectorType(active_connectors[0].connector_type)


async def resolve_client_for_category(
    functional_category: str,
    user_id: UUID,
    deps: ToolDependencies,
) -> tuple[Any, ConnectorType]:
    """
    Resolve the active client and connector type for a functional category.

    Used by HITL execute functions to dynamically resolve the active provider
    instead of hardcoding Google connector types.

    Args:
        functional_category: Category name ("email", "calendar", "contacts").
        user_id: User UUID.
        deps: ToolDependencies for getting connector service.

    Returns:
        Tuple of (client instance, resolved ConnectorType).

    Raises:
        ConnectorNotEnabledError: If no connector is active for this category.
    """
    from src.domains.agents.tools.exceptions import ConnectorNotEnabledError
    from src.domains.connectors.clients.registry import ClientRegistry

    connector_service = await deps.get_connector_service()
    resolved_type = await resolve_active_connector(user_id, functional_category, connector_service)

    if resolved_type is None:
        display_name = CATEGORY_DISPLAY_NAMES.get(functional_category, functional_category)
        raise ConnectorNotEnabledError(
            f"No {display_name} service is enabled. "
            "Go to Settings > Connectors to activate one.",
            connector_name=display_name,
        )

    if resolved_type.is_apple:
        credentials = await connector_service.get_apple_credentials(user_id, resolved_type)
    else:
        credentials = await connector_service.get_connector_credentials(user_id, resolved_type)

    if not credentials:
        raise ConnectorNotEnabledError(
            f"Credentials not found for {resolved_type.value}",
            connector_name=resolved_type.value,
        )

    client_class = ClientRegistry.get_client_class(resolved_type)
    if client_class is None:
        raise ConnectorNotEnabledError(
            f"No client registered for {resolved_type.value}",
            connector_name=resolved_type.value,
        )

    client = client_class(user_id, credentials, connector_service)
    return client, resolved_type
