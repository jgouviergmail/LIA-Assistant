"""Shared current-owner connector preference reads and writes, without provider work."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, raise_user_not_found
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.preferences.registry import get_preference_schema
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.preferences.service import ConnectorPreferencesService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository

_VALUES: TypeAdapter[dict[str, str | None]] = TypeAdapter(dict[str, str | None])


class ConnectorPreferenceStateUnavailable(ValueError):
    """A saved/encrypted preference cannot be read or persisted safely."""


class ConnectorPreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    connector_type: ConnectorType
    status: ConnectorStatus
    oauth_grant_id: UUID | None = None
    account_email: str | None = Field(default=None, max_length=320, strict=True)
    preferences: dict[str, str | None]


def connector_preference_snapshot(connector: Connector) -> ConnectorPreferenceSnapshot:
    schema = get_preference_schema(connector.connector_type.value)
    if schema is None:
        raise ValueError("Connector preferences are unsupported")
    try:
        prefs = (
            schema.model_validate_json(decrypt_data(connector.preferences_encrypted))
            if connector.preferences_encrypted
            else schema.model_validate({})
        )
        values = _VALUES.validate_python(prefs.model_dump(), strict=True)
        return ConnectorPreferenceSnapshot(
            id=connector.id,
            connector_type=connector.connector_type,
            status=connector.status,
            oauth_grant_id=connector.oauth_grant_id,
            account_email=(connector.connector_metadata or {}).get("oauth_account_email"),
            preferences=values,
        )
    except ValueError:
        # A corrupt encrypted record is unknown; never overwrite it as defaults.
        raise ConnectorPreferenceStateUnavailable(
            "Saved connector preferences unavailable"
        ) from None


async def owned_preference_connector(
    db: AsyncSession, actor_id: UUID, connector_id: UUID, *, lock: bool = False
) -> Connector:
    query = select(Connector).where(Connector.id == connector_id, Connector.user_id == actor_id)
    if lock:
        actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
        if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
            raise_user_not_found(actor_id)
        query = query.with_for_update()
    connector: Connector | None = await db.scalar(query.execution_options(populate_existing=True))
    if connector is None or connector.id != connector_id or connector.user_id != actor_id:
        raise ResourceNotFoundError("connector", str(connector_id))
    if get_preference_schema(connector.connector_type.value) is None:
        from src.core.exceptions import raise_connector_type_no_preferences

        raise_connector_type_no_preferences(connector.connector_type.value)
    return connector


async def update_owned_connector_preferences(
    db: AsyncSession,
    actor_id: UUID,
    connector_id: UUID,
    change: PreferencesRequest,
    *,
    expected: ConnectorPreferenceSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> ConnectorPreferenceSnapshot:
    connector = await owned_preference_connector(db, actor_id, connector_id, lock=True)
    before = connector_preference_snapshot(connector)
    if expected is not None and before != expected:
        raise ResourceConflictError("connector_preferences", detail={"error_code": "STALE_STATE"})
    sanitized = ConnectorPreferencesService.validate_and_sanitize(
        connector.connector_type.value,
        change.model_dump(exclude_none=True),
    )
    values = _VALUES.validate_python(sanitized.model_dump(), strict=True)
    after = before.model_copy(update={"preferences": values})
    if before == after:
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return after
    try:
        encrypted = encrypt_data(sanitized.model_dump_json())
    except Exception:
        raise ConnectorPreferenceStateUnavailable(
            "Connector preference encryption unavailable"
        ) from None
    connector.preferences_encrypted = encrypted
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return after
