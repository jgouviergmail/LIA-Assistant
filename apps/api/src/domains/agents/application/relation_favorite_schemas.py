"""The model selects a displayed name and state, never an owner or comparison proof."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from src.domains.relations.favorite_commands import RelationFavoriteSelection
from src.domains.shared.text_normalization import fold_name


class RelationFavoriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: StrictStr = Field(min_length=1, max_length=255)
    starred: StrictBool

    @model_validator(mode="after")
    def require_foldable_name(self) -> Self:
        key = fold_name(self.name)
        if not key or len(key) > 255:
            raise ValueError("A bounded relationship name is required")
        return self


class RelationFavoriteValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: RelationFavoriteSelection
    starred: StrictBool


class RelationFavoritePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relation_favorite: RelationFavoriteValues


class RelationActionField(StrEnum):
    FAVORITE = "relation_favorite"
    GROUPING = "relation_grouping"
    DEBRIEF = "relation_debrief"
    CONTEXT = "relation_context"
