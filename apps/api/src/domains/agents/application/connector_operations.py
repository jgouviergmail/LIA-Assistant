"""Non-secret connector preference snapshots and proposals reuse their actual domain owner."""

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.connector_schemas import (
    ConnectorPreferencePatch,
    ConnectorPreferencesProjection,
    ConnectorPreferencesRead,
    ConnectorPreferenceUpdateRequest,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.preparation import _preference_content
from src.domains.connectors.models import Connector, ConnectorType
from src.domains.connectors.preferences.commands import (
    connector_preference_snapshot,
    owned_preference_connector,
)
from src.domains.connectors.preferences.registry import CONNECTOR_PREFERENCES_REGISTRY
from src.domains.connectors.preferences.service import ConnectorPreferencesService

_VALUES: TypeAdapter[dict[str, str | None]] = TypeAdapter(dict[str, str | None])


async def read_connector_preferences(
    db: AsyncSession, actor_id: UUID, request: ConnectorPreferencesRead
) -> ConnectorPreferencesProjection:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    filters = (
        Connector.user_id == actor_id,
        Connector.connector_type.in_(
            [ConnectorType(kind) for kind in CONNECTOR_PREFERENCES_REGISTRY]
        ),
    )
    total = await db.scalar(select(func.count()).select_from(Connector).where(*filters))
    query = select(Connector).where(*filters).order_by(Connector.id).limit(request.limit + 1)
    if request.after_id is not None:
        query = query.where(Connector.id > request.after_id)
    connectors = list((await db.scalars(query.execution_options(populate_existing=True))).all())
    values = [connector_preference_snapshot(connector) for connector in connectors[: request.limit]]
    return ConnectorPreferencesProjection(
        connectors=values,
        total=total or 0,
        next_cursor=values[-1].id if len(connectors) > request.limit else None,
    )


async def prepare_connector_preference_content(
    db: AsyncSession,
    actor_id: UUID,
    request: ConnectorPreferenceUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    connector = await owned_preference_connector(db, actor_id, request.connector_id)
    before = connector_preference_snapshot(connector)
    sanitized = ConnectorPreferencesService.validate_and_sanitize(
        connector.connector_type.value,
        request.preferences.model_dump(exclude_none=True),
    )
    desired = before.model_copy(
        update={"preferences": _VALUES.validate_python(sanitized.model_dump(), strict=True)}
    )
    return _preference_content(
        actor_id,
        ConnectorPreferencePatch(connector_preferences=desired),
        {"connector_preferences": before.model_dump(mode="json")},
        command_id=command_id,
    )
