"""Fresh connection card projections and effect-free, exact local unlink proposals."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionsProjection,
    ConnectorConnectionsRead,
    ConnectorConnectionUnlinkPatch,
    ConnectorConnectionValue,
    ConnectorUnlinkRequest,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.preparation import _preference_content
from src.domains.connectors.models import Connector
from src.domains.connectors.removal_commands import (
    connector_removal_snapshot,
    owned_connector_for_removal,
)


async def read_connector_connections(
    db: AsyncSession,
    actor_id: UUID,
    request: ConnectorConnectionsRead,
) -> ConnectorConnectionsProjection:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    filters = [Connector.user_id == actor_id]
    if request.connector_id is not None:
        filters.append(Connector.id == request.connector_id)
    total = await db.scalar(select(func.count()).select_from(Connector).where(*filters))
    query = select(Connector).where(*filters).order_by(Connector.id).limit(request.limit + 1)
    if request.after_id is not None:
        query = query.where(Connector.id > request.after_id)
    rows = list((await db.scalars(query.execution_options(populate_existing=True))).all())
    values = [
        ConnectorConnectionValue.model_validate(
            connector_removal_snapshot(row).model_dump(mode="json", exclude={"oauth_grant_id"})
        )
        for row in rows[: request.limit]
    ]
    return ConnectorConnectionsProjection(
        connectors=values,
        total=total or 0,
        next_cursor=values[-1].id if len(rows) > request.limit else None,
    )


async def prepare_connector_unlink_content(
    db: AsyncSession,
    actor_id: UUID,
    request: ConnectorUnlinkRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    before = connector_removal_snapshot(
        await owned_connector_for_removal(db, actor_id, request.connector_id)
    )
    return _preference_content(
        actor_id,
        ConnectorConnectionUnlinkPatch(connector_to_disconnect=before),
        {"connector_to_disconnect": before.model_dump(mode="json")},
        command_id=command_id,
    )
