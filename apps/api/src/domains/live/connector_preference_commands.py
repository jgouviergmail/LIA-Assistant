"""Live connector settings share one current-owner write path for UI and assistant."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.live.model_settings import LiveModelSettings, write_models, write_session_budget
from src.domains.live.preferences import read_live_preferences
from src.domains.live.providers import PROVIDERS
from src.domains.live.schemas import LiveConnectorSettings
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.live_connector_preferences import LiveConnectorPreferenceSnapshot


def connector_preference_snapshot(
    actor: User, connector: Connector, provider: str
) -> LiveConnectorPreferenceSnapshot:
    raw = json.dumps(
        {
            "metadata": connector.connector_metadata,
            "credentials": connector.credentials_encrypted,
            "active_provider": read_live_preferences(actor.live_preferences).provider,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return LiveConnectorPreferenceSnapshot(
        connector_id=connector.id,
        connector_type=connector.connector_type,
        status=connector.status,
        provider=provider,
        stored_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


async def locked_live_connector(
    db: AsyncSession,
    actor_id: UUID,
    provider_id: str,
    *,
    locate: Callable[[User, str], Awaitable[Connector]],
) -> tuple[User, Connector]:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    selected = await locate(actor, provider_id)
    connector = await db.scalar(
        select(Connector)
        .where(
            Connector.id == selected.id,
            Connector.user_id == actor_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        connector is None
        or connector.user_id != actor_id
        or connector.status != ConnectorStatus.ACTIVE
        or ConnectorType(connector.connector_type) not in PROVIDERS
        or PROVIDERS[ConnectorType(connector.connector_type)].provider_id != provider_id
    ):
        raise ResourceConflictError("live connector", detail={"error_code": "STALE_STATE"})
    return actor, connector


async def update_live_connector_settings(
    db: AsyncSession,
    actor_id: UUID,
    provider_id: str,
    desired: LiveConnectorSettings,
    *,
    locate: Callable[[User, str], Awaitable[Connector]],
    validate: Callable[[User, Connector, LiveConnectorSettings], Awaitable[None]],
    expected: LiveConnectorPreferenceSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> Connector:
    actor, connector = await locked_live_connector(db, actor_id, provider_id, locate=locate)
    snapshot = connector_preference_snapshot(actor, connector, provider_id)
    if expected is not None and snapshot != expected:
        raise ResourceConflictError("live connector", detail={"error_code": "STALE_STATE"})
    metadata = write_session_budget(
        write_models(
            connector.connector_metadata,
            desired.model,
            LiveModelSettings(**desired.model_dump(exclude={"model"})),
        ),
        desired.session_budget_eur,
    )
    preferences = {**(actor.live_preferences or {}), "provider": provider_id}
    if metadata == connector.connector_metadata and preferences == actor.live_preferences:
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return connector
    await validate(actor, connector, desired)
    connector.connector_metadata = metadata
    actor.live_preferences = preferences
    db.add(actor)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return connector
