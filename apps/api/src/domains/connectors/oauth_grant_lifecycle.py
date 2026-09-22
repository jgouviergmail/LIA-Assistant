"""Deletion and provider revocation of shared connector OAuth grants."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_invalid_input
from src.domains.connectors.models import Connector, OAuthGrant
from src.domains.connectors.repository import ConnectorRepository


async def delete_shared_connector(
    db: AsyncSession, repository: ConnectorRepository, connector: Connector
) -> None:
    """Remove one service and discard its local grant after the final unlink."""
    grant = await db.scalar(
        select(OAuthGrant)
        .where(OAuthGrant.id == connector.oauth_grant_id, OAuthGrant.user_id == connector.user_id)
        .with_for_update()
    )
    if grant is None:
        raise_invalid_input("Shared OAuth grant is missing", connector_id=str(connector.id))
    sibling = await db.scalar(
        select(Connector.id).where(
            Connector.oauth_grant_id == grant.id,
            Connector.id != connector.id,
        )
    )
    await repository.delete(connector)
    await db.flush()
    if sibling is None:
        await db.delete(grant)
    await db.commit()
