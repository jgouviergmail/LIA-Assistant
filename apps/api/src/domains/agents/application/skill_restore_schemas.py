"""Exact consent to put a skill's previous version back: the skill, and when that version left.

The version's own words and files stay private: the proposal seals a digest of them, compared
again at the confirmation, so a version replaced meanwhile is never restored on an old consent.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem


class SkillRestoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: UUID


class SkillRestoreSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillRestoreInput
    skill: SkillReadItem
    previous_version_at: AwareDatetime
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest"})

    def restored_scope(self) -> dict[str, JsonValue]:
        """What the confirmation says comes back: this skill, as it was when put aside."""
        public = self.public_scope()
        return {"name": self.skill.name, "version_put_aside_at": public["previous_version_at"]}


class SkillRestorePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_to_restore: SkillRestoreSnapshot


class SkillRestoreField(StrEnum):
    RESTORE = "skill_to_restore"


def canonical_skill_restore(draft: ApplicationActionDraftContent) -> bool:
    selected = SkillRestorePatch.model_validate(draft.intent).skill_to_restore
    return draft.before == {"skill_to_restore": selected.public_scope()} and draft.after == {
        "skill_to_restore": selected.restored_scope()
    }
