"""Strict UI library queries with bounded list windows and original typed responses."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.core.constants import SKILL_LIBRARY_QUERY_MAX_CHARS
from src.domains.skill_library.schemas import (
    LibraryInstalledResponse,
    LibraryPreviewAnswer,
    LibrarySearchResponse,
    LibraryUpdatePreviewResponse,
)


class _LibraryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LibrarySearchInput(_LibraryQuery):
    kind: Literal["search"]
    q: str = Field(max_length=SKILL_LIBRARY_QUERY_MAX_CHARS)
    portal: str | None = Field(default=None, max_length=40)


class LibraryPreviewInput(_LibraryQuery):
    kind: Literal["preview"]
    repository: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    skill_id: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=500)
    ref: str | None = Field(default=None, max_length=200)
    portal: str | None = Field(default=None, max_length=40)
    registry_id: str | None = Field(default=None, max_length=300)


class LibraryInstalledInput(_LibraryQuery):
    kind: Literal["installed"]


class LibraryUpdatePreviewInput(_LibraryQuery):
    kind: Literal["update_preview"]
    skill_id: UUID


class SkillLibraryReadInput(_LibraryQuery):
    request: Annotated[
        LibrarySearchInput
        | LibraryPreviewInput
        | LibraryInstalledInput
        | LibraryUpdatePreviewInput,
        Field(discriminator="kind"),
    ]
    limit: StrictInt = Field(default=20, ge=1, le=100)
    offset: StrictInt = Field(default=0, ge=0)


class LibraryListWindow(_LibraryQuery):
    total: int
    next_offset: int | None


LibraryReadData = (
    LibraryInstalledResponse
    | LibraryPreviewAnswer
    | LibrarySearchResponse
    | LibraryUpdatePreviewResponse
)
LibraryListPath = Literal[
    "items",
    "preview.files",
    "preview.skipped",
    "preview.audits",
    "choice.folders",
    "changes.added",
    "changes.removed",
    "changes.modified",
]


class SkillLibraryReadProjection(_LibraryQuery):
    observed_at: AwareDatetime
    data: LibraryReadData
    windows: dict[LibraryListPath, LibraryListWindow]
