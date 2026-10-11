"""Explicit bounded MCP metadata; cached schemas, endpoints and errors stay private."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.infrastructure.mcp.personal_metadata_contract import (
    PersonalMCPReadItem as PersonalMCPReadItem,
)
from src.infrastructure.mcp.personal_metadata_contract import (
    PersonalMCPToolItem as PersonalMCPToolItem,
)


class PersonalMCPReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID | None = None
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=20, ge=1, le=50)
    tools_offset: StrictInt = Field(default=0, ge=0)
    tools_limit: StrictInt = Field(default=10, ge=1, le=50)


class PersonalMCPReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: AwareDatetime
    items: tuple[PersonalMCPReadItem, ...]
    total: int
    next_offset: int | None
