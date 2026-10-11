"""The model chooses only an optional exact target; local bytes require browser consent."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem


class SkillFileUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    replace_skill_id: UUID | None = None


class SkillFileUploadSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillFileUploadInput
    previous: SkillReadItem | None
    max_file_size_bytes: StrictInt = Field(ge=1)
    max_package_files: StrictInt = Field(ge=1)
    max_decompressed_bytes: StrictInt = Field(ge=1)
    max_personal_skills: StrictInt = Field(ge=1)
    state_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", repr=False)

    @model_validator(mode="after")
    def exact_replacement(self) -> SkillFileUploadSelection:
        if self.previous is None:
            if self.request.replace_skill_id is not None or self.state_digest is not None:
                raise ValueError("A new skill cannot carry a replacement identity or witness")
        elif self.request.replace_skill_id != self.previous.skill_id or self.state_digest is None:
            raise ValueError("Replacement identity, metadata and witness must agree")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"state_digest"}),
            "allowed_extensions": [".md", ".zip"],
            "browser_file_confirmation_required": True,
        }


class SkillFileUploadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_file_upload: SkillFileUploadSelection


class SkillFileUploadField(StrEnum):
    UPLOAD = "skill_file_upload"


def canonical_skill_file_upload(draft: ApplicationActionDraftContent) -> bool:
    selected = SkillFileUploadPatch.model_validate(draft.intent).skill_file_upload
    return draft.before == {
        "skill_file_upload": (
            selected.previous.model_dump(mode="json") if selected.previous else None
        )
    } and draft.after == {"skill_file_upload": selected.public_scope()}
