"""Strict current-account gallery filters publish the same bounds as the UI."""

from datetime import datetime
from typing import Literal, Self, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.domains.attachments.gallery_projection import (
    GALLERY_DEFAULT_LIMIT,
    GALLERY_MAX_LIMIT,
    GALLERY_MIN_LIMIT,
    GALLERY_QUERY_MAX_LENGTH,
    GalleryFamily,
)
from src.domains.attachments.gallery_queries import GALLERY_SORTS
from src.domains.attachments.schemas import GeneratedAssetListResponse

GallerySort = Literal["created_desc", "created_asc", "expires_asc", "name_asc"]
GALLERY_READ_MAX_BYTES = 64_000
assert set(get_args(GallerySort)) == GALLERY_SORTS


class GalleryReadQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    family: GalleryFamily
    q: str | None = Field(default=None, max_length=GALLERY_QUERY_MAX_LENGTH)
    created_after: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    expires_before: AwareDatetime | None = None
    sort: GallerySort = "created_desc"
    limit: StrictInt = Field(
        default=GALLERY_DEFAULT_LIMIT, ge=GALLERY_MIN_LIMIT, le=GALLERY_MAX_LIMIT
    )
    offset: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after > self.created_before
        ):
            raise ValueError("created_after cannot be later than created_before")
        return self


class GalleryReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family: GalleryFamily
    observed_at: datetime
    page: GeneratedAssetListResponse
    next_offset: StrictInt | None = None
