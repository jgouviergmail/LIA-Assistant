"""Public local CRM cards are bounded source projections with explicit truncation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.relations.schemas import RelationDetail, RelationsOverview, RelationSummary

RELATION_DATA_MAX_ITEMS = 50


class RelationDataRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional displayed name for its local relationship card; omitted reads the overview",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=RELATION_DATA_MAX_ITEMS,
        strict=True,
        description="Maximum relationships, items per local card section and merged spellings returned; source caps also apply",
    )

    offset: int = Field(
        default=0,
        ge=0,
        strict=True,
        description="Skip this many items in each live source UI list. Pagination cannot read past source UI caps; retain the same selector and limit.",
    )

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A relationship name cannot be whitespace only")
        return value


class BoundedRelationsOverview(RelationsOverview):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relations: list[RelationSummary] = Field(max_length=RELATION_DATA_MAX_ITEMS)


class BoundedRelationDetail(RelationDetail):
    model_config = ConfigDict(frozen=True, extra="forbid")
    merged_from: list[str] = Field(default_factory=list, max_length=RELATION_DATA_MAX_ITEMS)
    merged_from_total: int = Field(ge=0)


class RelationDataProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    overview: BoundedRelationsOverview | None
    detail: BoundedRelationDetail | None
    overview_truncated: bool
    detail_truncated: bool
    peer_data_best_effort: bool = True
    next_offset: int | None = None
    observed_at: datetime
