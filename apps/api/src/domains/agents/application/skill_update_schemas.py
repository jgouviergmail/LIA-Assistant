"""Consent seals exact public skill identity and changes only one personal switch."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem


class SkillUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_id: UUID
    enabled: StrictBool


class SkillUpdateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillUpdateInput
    expected: SkillReadItem


class SkillUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_personal_state: SkillUpdateObservation


class SkillUpdateField(StrEnum):
    STATE = "skill_personal_state"


def canonical_skill_update(draft: ApplicationActionDraftContent) -> bool:
    selected = SkillUpdatePatch.model_validate(draft.intent).skill_personal_state
    return draft.before == {
        "skill_personal_state": selected.expected.model_dump(mode="json")
    } and draft.after == {
        "skill_personal_state": selected.expected.model_copy(
            update={"enabled_for_user": selected.request.enabled}
        ).model_dump(mode="json")
    }
