"""Explicit source grouping selectors reject guessed identities and injected authority."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from src.domains.relations.grouping_commands import RelationGroupingSelection
from src.domains.relations.schemas import RelationMergeRequest
from src.domains.shared.text_normalization import fold_name


class RelationGroupingRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["merge", "split"]
    source: StrictStr = Field(
        min_length=1, max_length=255, description="Displayed name to merge away or split back out"
    )
    target: StrictStr | None = Field(
        default=None, min_length=1, max_length=255, description="Displayed target for merge only"
    )

    @model_validator(mode="after")
    def validate_source_identity(self) -> Self:
        source_key = fold_name(self.source)
        if not source_key or len(source_key) > 255:
            raise ValueError("A bounded source name is required")
        if self.action == "split":
            if self.target is not None:
                raise ValueError("A split has no target")
            return self
        target_key = fold_name(self.target or "")
        if not target_key or len(target_key) > 255:
            raise ValueError("A merge requires a bounded target name")
        if source_key == target_key:
            raise ValueError("Source and target are the same relationship")
        return self


class RelationGroupingPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relation_grouping: RelationGroupingSelection


if set(RelationMergeRequest.model_fields) != {"source", "target"}:
    raise AssertionError(
        "New source grouping options require reviewed native selection and confirmation"
    )
