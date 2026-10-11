"""Connection cards expose finite saved identities and prepare local unlink only."""

from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.removal_commands import ConnectorRemovalSnapshot
from src.domains.connectors.schemas import ConnectorResponse


class ConnectorConnectionField(str, Enum):
    CONNECTION = "connector_to_disconnect"


class ConnectorConnectionsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: UUID | None = None
    after_id: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)


class ConnectorUnlinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: UUID


class ConnectorConnectionUnlinkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connector_to_disconnect: ConnectorRemovalSnapshot


class ConnectorConnectionValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    connector_type: ConnectorType
    status: ConnectorStatus
    account_email: str | None = Field(default=None, strict=True, max_length=320)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ConnectorConnectionsProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connectors: list[ConnectorConnectionValue]
    total: int
    next_cursor: UUID | None = None


def assert_connection_projection_coverage() -> None:
    # Account ownership and grant identity are host-only. Granted scopes and
    # service metadata belong to their dedicated, sanitized settings projections.
    # The derived reconnect hint belongs to the secure authorization handoff.
    source_only = {"user_id", "oauth_grant_id", "scopes", "metadata", "bulk_reconnect_provider"}
    mapped = {"account_email": "metadata"}
    public = set(ConnectorConnectionValue.model_fields)
    projected = {mapped.get(field, field) for field in public}
    if set(ConnectorResponse.model_fields) != projected | source_only:
        raise AssertionError("New connection card fields require explicit projection review")


assert_connection_projection_coverage()
