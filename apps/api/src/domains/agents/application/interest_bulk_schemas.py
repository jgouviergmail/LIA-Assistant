"""A complete-scope confirmation carries bounded summaries and a private digest."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.interests.models import InterestCategory, InterestStatus


class InterestBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["all_owned"]


class InterestBulkSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    selected_count: int = Field(ge=0)
    by_category: dict[str, int]
    by_status: dict[str, int]
    unknown_category_count: int = Field(ge=0)
    unknown_status_count: int = Field(ge=0)
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def complete_bounded_counts(self) -> Self:
        for counts, vocabulary, unknown in (
            (
                self.by_category,
                {item.value for item in InterestCategory},
                self.unknown_category_count,
            ),
            (self.by_status, {item.value for item in InterestStatus}, self.unknown_status_count),
        ):
            if (
                not set(counts) <= vocabulary
                or any(count < 0 for count in counts.values())
                or sum(counts.values()) + unknown != self.selected_count
            ):
                raise ValueError("Erasure summaries must cover the complete source selection")
        return self


class InterestBulkDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interests_to_delete: InterestBulkSnapshot
