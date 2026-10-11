"""Strict public skill-gallery metadata, never cached instructions or disk paths."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.domains.skills.models import SkillProvenance


class SkillReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: StrictInt = Field(default=20, ge=1, le=100)
    offset: StrictInt = Field(default=0, ge=0)


class SkillReadItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str
    descriptions: dict[str, str] | None
    scope: Literal["admin", "user"]
    category: str | None
    priority: int
    always_loaded: bool
    has_scripts: bool
    has_plan_template: bool
    enabled_for_user: bool
    admin_enabled: bool
    dialogue: bool
    outputs: list[str] | None
    skill_id: UUID
    provenance: SkillProvenance | None


class SkillReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: AwareDatetime
    items: tuple[SkillReadItem, ...]
    total: int
    next_offset: int | None
