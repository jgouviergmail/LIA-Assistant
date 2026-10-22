"""Fresh locked connection identity for local unlink, shared by HTTP and native confirmation."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    raise_invalid_input,
    raise_user_not_found,
)
from src.domains.connectors.models import (
    Connector,
    ConnectorStatus,
    ConnectorType,
    OAuthGrant,
    get_functional_category,
)
from src.domains.connectors.oauth_grant_lifecycle import delete_shared_connector
from src.domains.connectors.provider_resolver import LEGACY_CONNECTOR_ALIASES
from src.domains.connectors.repository import ConnectorRepository
from src.domains.shared.discussion_catalogue import SOURCE_REGISTRY
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.discussion_invalidation import invalidate_discussion_sources

logger = structlog.get_logger(__name__)


class ConnectorIdentityUnavailable(ValueError):
    """A saved connection identity cannot be projected safely."""


def discussion_sources_of(connector_type: ConnectorType) -> tuple[SourceKey, ...]:
    """The discussion sources a connector of this type serves, from the source catalogue.

    Args:
        connector_type: The connector's type; a legacy alias reads as its canonical type.

    Returns:
        The sources whose ``connector_category`` is the type's category, in catalogue
        order; empty for a connector no discussion source reads.
    """
    category = get_functional_category(LEGACY_CONNECTOR_ALIASES.get(connector_type, connector_type))
    return tuple(
        source
        for source, definition in SOURCE_REGISTRY.items()
        if category is not None and definition.connector_category == category
    )


async def remove_owned_connector(
    db: AsyncSession,
    repository: ConnectorRepository,
    actor_id: UUID,
    connector_id: UUID,
    *,
    legacy_cleanup: Callable[[Connector], Awaitable[None]],
    invalidate: Callable[[UUID], Awaitable[None]],
    expected: ConnectorRemovalSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> None:
    """Share the actual local unlink transaction and its post-commit invalidation."""
    connector = await locked_connector_for_removal(db, actor_id, connector_id, expected=expected)
    await invalidate_discussion_sources(
        db, actor_id, discussion_sources_of(connector.connector_type)
    )
    if connector.oauth_grant_id:
        await delete_shared_connector(db, repository, connector)
    else:
        await legacy_cleanup(connector)
        await repository.delete(connector)
        await db.commit()
    if receipt is not None:
        receipt.committed = True
    logger.info(
        "connector_deleted",
        user_id=str(actor_id),
        connector_id=str(connector_id),
        connector_type=connector.connector_type,
    )
    await invalidate(actor_id)


class ConnectorRemovalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    connector_type: ConnectorType
    status: ConnectorStatus
    oauth_grant_id: UUID | None
    account_email: str | None = Field(default=None, strict=True, max_length=320)
    created_at: AwareDatetime
    updated_at: AwareDatetime


def connector_removal_snapshot(connector: Connector) -> ConnectorRemovalSnapshot:
    metadata = connector.connector_metadata
    if metadata is not None and not isinstance(metadata, dict):
        raise ConnectorIdentityUnavailable("Connection identity unavailable")
    try:
        return ConnectorRemovalSnapshot(
            id=connector.id,
            connector_type=connector.connector_type,
            status=connector.status,
            oauth_grant_id=connector.oauth_grant_id,
            account_email=(metadata or {}).get("oauth_account_email"),
            created_at=connector.created_at,
            updated_at=connector.updated_at,
        )
    except ValidationError:
        raise ConnectorIdentityUnavailable("Connection identity unavailable") from None


async def owned_connector_for_removal(
    db: AsyncSession,
    actor_id: UUID,
    connector_id: UUID,
    *,
    lock: bool = False,
    stale_if_missing: bool = False,
) -> Connector:
    query = select(Connector).where(Connector.id == connector_id, Connector.user_id == actor_id)
    if lock:
        query = query.with_for_update()
    connector: Connector | None = await db.scalar(query.execution_options(populate_existing=True))
    if connector is None or connector.id != connector_id or connector.user_id != actor_id:
        if stale_if_missing:
            raise ResourceConflictError("connector", detail={"error_code": "STALE_STATE"})
        raise ResourceNotFoundError("connector", str(connector_id))
    return connector


async def locked_connector_for_removal(
    db: AsyncSession,
    actor_id: UUID,
    connector_id: UUID,
    *,
    expected: ConnectorRemovalSnapshot | None = None,
) -> Connector:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise_user_not_found(actor_id)
    candidate = await owned_connector_for_removal(
        db, actor_id, connector_id, stale_if_missing=expected is not None
    )
    grant_id = candidate.oauth_grant_id
    # OAuth writers acquire Grant -> Connector. Hold the same order after the
    # account lock; taking the connection first would deadlock with relinking.
    if grant_id is not None:
        grant: OAuthGrant | None = await db.scalar(
            select(OAuthGrant)
            .where(OAuthGrant.id == grant_id, OAuthGrant.user_id == actor_id)
            .with_for_update()
        )
        if grant is None or grant.id != grant_id or grant.user_id != actor_id:
            raise_invalid_input("Shared OAuth grant is missing")
    connector = await owned_connector_for_removal(
        db, actor_id, connector_id, lock=True, stale_if_missing=expected is not None
    )
    if connector.oauth_grant_id != grant_id or (
        expected is not None and connector_removal_snapshot(connector) != expected
    ):
        raise ResourceConflictError("connector", detail={"error_code": "STALE_STATE"})
    return connector
