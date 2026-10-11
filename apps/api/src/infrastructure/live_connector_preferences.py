"""Typed injected Live settings boundary; private snapshots never enter model requests."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.users.preference_cas import PreferenceWriteReceipt


class LiveConnectorPreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connector_id: UUID
    connector_type: ConnectorType
    status: ConnectorStatus
    provider: str = Field(min_length=1, max_length=32, strict=True)
    stored_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class LiveConnectorSettingsRefused(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LiveConnectorPreferenceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connectors: list[dict[str, JsonValue]]
    active_provider: str | None
    configuration: dict[str, JsonValue] = Field(default_factory=dict)


class LiveOptionsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choices: list[dict[str, JsonValue]]
    details: dict[str, JsonValue]


class LiveOptionsPage(LiveOptionsProjection):
    total: StrictInt = Field(ge=0)
    page_offset: StrictInt = Field(ge=0)
    catalogue_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    next_cursor: StrictStr | None = Field(pattern=r"^[0-9a-f]{64}:[1-9][0-9]{0,4}$")


class LiveConnectorSettingValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: StrictStr = Field(min_length=1, max_length=120)
    voice: StrictStr = Field(min_length=1, max_length=64)
    thinking_level: StrictStr | None = Field(default=None, max_length=16)
    idle_timeout_seconds: StrictInt
    session_max_minutes: StrictInt
    session_budget_eur: FiniteFloat | None = None


class LiveConnectorSettingsGateway(Protocol):
    async def options(
        self, db: AsyncSession, actor_id: UUID, section: str, provider: str | None, *, language: str
    ) -> LiveOptionsProjection: ...
    async def prepare(
        self, db: AsyncSession, actor_id: UUID, provider: str, change: dict[str, JsonValue]
    ) -> tuple[
        LiveConnectorPreferenceSnapshot, LiveConnectorSettingValues, LiveConnectorSettingValues
    ]: ...
    async def read(self, db: AsyncSession, actor_id: UUID) -> LiveConnectorPreferenceProjection: ...
    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        provider: str,
        settings: dict[str, JsonValue],
        *,
        expected: LiveConnectorPreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
        language: str,
    ) -> None: ...


_gateway: LiveConnectorSettingsGateway | None = None


def configure_live_connector_preferences(
    gateway: LiveConnectorSettingsGateway | None,
) -> LiveConnectorSettingsGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_live_connector_preferences() -> LiveConnectorSettingsGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
