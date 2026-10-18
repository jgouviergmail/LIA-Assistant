"""Strict public plugin metadata, independent of credentials and package instructions."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt


class PluginReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: StrictInt = Field(default=20, ge=1, le=100)
    offset: StrictInt = Field(default=0, ge=0)


class PluginReadItem(BaseModel):
    """Assistant inventory is closed independently of settings-only metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)
    id: UUID
    name: str
    version: str | None = None
    description: str | None = None
    spec_version: str
    skill_names: list[str] = Field(default_factory=list)
    server_names: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PluginReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: AwareDatetime
    items: tuple[PluginReadItem, ...]
    total: int
    next_offset: int | None
