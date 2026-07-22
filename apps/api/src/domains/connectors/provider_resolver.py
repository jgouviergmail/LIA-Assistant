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
    from src.domains.agents.tools.exceptions import ConnectorNotEnabledError

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


async def find_error_connector_type(
    user_id: UUID,
    functional_category: str,
    connector_service: Any,
) -> str | None:
    """Return the category's connector stuck in ``status=ERROR``, if any.

    ADR-134 V2: on runs after a connector broke, it is no longer resolved as
    the active provider and tools only report "no connector". This lookup lets
    the raise/emission sites distinguish "nothing configured" from "the
    provider is broken and one click away from repair" — only the latter may
    show a "Reconnect" banner.

    ``REVOKED`` is deliberately NOT eligible: a deliberate disconnection must
    not be nagged about (arbitration 2026-07-21). Uses the same Redis-cached
    ``get_user_connectors()`` as :func:`resolve_active_connector` — no extra
    DB query, and this only runs on the failure path.

    Args:
        user_id: User UUID.
        functional_category: Category name ("email", "calendar", ...).
        connector_service: ConnectorService instance.

    Returns:
        The canonical connector type value (e.g. ``"google_gmail"``), or None.
    """
    category_types = CONNECTOR_FUNCTIONAL_CATEGORIES.get(functional_category)
    if category_types is None:
        return None

    response = await connector_service.get_user_connectors(user_id)
    for connector in response.connectors:
        ct = connector.connector_type
        canonical_ct = _LEGACY_CONNECTOR_ALIASES.get(ct, ct)
        if canonical_ct in category_types and connector.status == ConnectorStatus.ERROR:
            return ConnectorType(canonical_ct).value
    return None


async def build_connector_not_enabled_error(
    message: str,
    *,
    connector_name: str,
    functional_category: str,
    user_id: UUID,
    connector_service: Any,
) -> ConnectorNotEnabledError:
    """Build a ``ConnectorNotEnabledError`` enriched with the broken connector.

    Best-effort enrichment: a failure while looking up the connector list must
    never mask the original "not enabled" error — the exception is then simply
    returned un-enriched (no banner, which is the safe default).

    Args:
        message: Human-readable message for the LLM/tool output.
        connector_name: Display name carried by the exception.
        functional_category: Category that failed to resolve.
        user_id: User UUID.
        connector_service: ConnectorService instance.

    Returns:
        The exception to raise (never raises itself).
    """
    from src.domains.agents.tools.exceptions import ConnectorNotEnabledError

    error_connector_type: str | None = None
    try:
        error_connector_type = await find_error_connector_type(
            user_id, functional_category, connector_service
        )
    except Exception as lookup_error:
        logger.debug(
            "error_connector_lookup_failed",
            functional_category=functional_category,
            error=str(lookup_error),
        )

    return ConnectorNotEnabledError(
        message,
        connector_name=connector_name,
        functional_category=functional_category,
        error_connector_type=error_connector_type,
    )


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
        # Enriched with the category's ERROR-status connector (if any) so the
        # central handler can surface the "Reconnect" banner (ADR-134 V2).
        raise await build_connector_not_enabled_error(
            f"No {display_name} service is enabled. "
            "Go to Settings > Connectors to activate one.",
            connector_name=display_name,
            functional_category=functional_category,
            user_id=user_id,
            connector_service=connector_service,
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
