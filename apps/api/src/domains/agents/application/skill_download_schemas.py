"""Archive consent exposes public metadata and size, never private instruction bytes or paths."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem


class SkillDownloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: UUID


class SkillDownloadSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillDownloadInput
    skill: SkillReadItem
    filename: str
    file_bytes: StrictInt = Field(ge=0)
    content_type: str = "application/zip"
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest"})


class SkillDownloadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_to_download: SkillDownloadSnapshot


def canonical_skill_download(draft: ApplicationActionDraftContent) -> bool:
    scope = SkillDownloadPatch.model_validate(draft.intent).skill_to_download
    return draft.before == {"skill_to_download": None} and draft.after == {
        "skill_to_download": scope.public_scope()
    }
