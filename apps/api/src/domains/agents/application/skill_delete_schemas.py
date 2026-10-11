"""Exact public skill deletion consent seals private directory/content witnesses."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem


class SkillDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: UUID


class SkillDeleteSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillDeleteInput
    skill: SkillReadItem
    files_present: bool
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest"})


class SkillDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_to_delete: SkillDeleteSnapshot


class SkillDeleteField(StrEnum):
    DELETE = "skill_to_delete"


def canonical_skill_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = SkillDeletePatch.model_validate(draft.intent).skill_to_delete
    return draft.before == {"skill_to_delete": selected.public_scope()} and draft.after == {
        "skill_to_delete": None
    }
