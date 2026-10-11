"""Strict public plugin metadata, independent of credentials and package instructions."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.domains.plugins.schemas import PluginResponse


class PluginReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: StrictInt = Field(default=20, ge=1, le=100)
    offset: StrictInt = Field(default=0, ge=0)


class PluginReadItem(PluginResponse):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class PluginReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: AwareDatetime
    items: tuple[PluginReadItem, ...]
    total: int
    next_offset: int | None
