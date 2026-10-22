"""Uncached provider selection for autonomous readers which must honor immediate withdrawal."""

from uuid import UUID

from sqlalchemy import select

from src.domains.connectors.keyless import is_keyless_available
from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    Connector,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.provider_resolver import LEGACY_CONNECTOR_ALIASES
from src.domains.connectors.service import ConnectorService
from src.domains.users.active_reader import require_active_owner_read


async def resolve_active_connector_fresh(
    owner: UUID, category: str, service: ConnectorService
) -> ConnectorType | None:
    """Return the connector type serving a category now, read without any cache.

    An autonomous reader must honour an immediate withdrawal: the most recently
    updated active connector of the category wins, unless an administrator
    disabled its type; otherwise a keyless instance provider when available.

    Args:
        owner: The account.
        category: The functional category.
        service: The connector service whose session is read.

    Returns:
        The connector type, or None when none serves the category.

    Raises:
        ValueError: The category is unknown.
    """
    await require_active_owner_read(service.db, owner)
    types = CONNECTOR_FUNCTIONAL_CATEGORIES.get(category)
    if types is None:
        raise ValueError("unknown connector category")
    legacy = tuple(
        kind for kind, canonical in LEGACY_CONNECTOR_ALIASES.items() if canonical in types
    )
    selected = await service.db.scalar(
        select(Connector.connector_type)
        .where(
            Connector.user_id == owner,
            Connector.connector_type.in_((*types, *legacy)),
            Connector.status == ConnectorStatus.ACTIVE,
        )
        .order_by(Connector.updated_at.desc(), Connector.id.desc())
        .limit(1)
    )
    if selected is not None:
        config = await service.repository.get_global_config_by_type(selected)
        return selected if config is None or config.is_enabled else None
    for kind in sorted(types, key=lambda value: value.value):
        if kind.is_keyless and await is_keyless_available(service.repository, kind):
            return kind
    return None
