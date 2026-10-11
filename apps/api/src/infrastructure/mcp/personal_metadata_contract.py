"""Typed personal MCP metadata port; consumers never import its business owner."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession


class PersonalMCPToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool_name: str
    description: str
    title: str | None


class PersonalMCPReadItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    name: str
    endpoint_host: str | None
    auth_type: Literal["none", "api_key", "bearer", "oauth2"]
    status: Literal["active", "inactive", "auth_required", "error"]
    is_enabled: bool
    plugin_id: UUID | None
    domain_description: str | None
    timeout_seconds: int
    hitl_required: bool | None
    iterative_mode: bool
    header_name: str | None
    has_credentials: bool
    has_oauth_credentials: bool
    oauth_scopes: str | None
    tool_count: int
    tools: tuple[PersonalMCPToolItem, ...]
    next_tool_offset: int | None
    last_connected_at: AwareDatetime | None
    has_connection_error: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PersonalMCPMetadataReader(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        *,
        server_id: UUID | None,
        offset: int,
        limit: int,
        tools_offset: int,
        tools_limit: int,
    ) -> tuple[tuple[PersonalMCPReadItem, ...], int]: ...
