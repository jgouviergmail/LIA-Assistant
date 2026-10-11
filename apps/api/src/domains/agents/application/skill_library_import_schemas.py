"""Sealed original library previews contain metadata, never executable skill bodies."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.skill_library.schemas import LibraryInstallRequest, LibraryUpdatePreviewResponse


class LibraryInstallInput(LibraryInstallRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LibraryUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: UUID
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class LibraryImportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["install", "update"]
    request: LibraryInstallInput | LibraryUpdateInput
    preview: LibraryUpdatePreviewResponse
    previous: dict[str, JsonValue] | None = None
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest", "request"})


class LibraryImportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_library_import: LibraryImportSnapshot


class LibraryImportField(StrEnum):
    IMPORT = "skill_library_import"


def canonical_library_import(draft: ApplicationActionDraftContent) -> bool:
    selected = LibraryImportPatch.model_validate(draft.intent).skill_library_import
    valid_request = (
        selected.kind == "install"
        and isinstance(selected.request, LibraryInstallInput)
        or selected.kind == "update"
        and isinstance(selected.request, LibraryUpdateInput)
    )
    return (
        bool(valid_request)
        and draft.before == {"skill_library_import": selected.previous}
        and draft.after == {"skill_library_import": selected.public_scope()}
    )
