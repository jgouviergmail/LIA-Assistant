"""A source build accepts explicit name/force; private comparison facts stay server-side."""

from inspect import signature

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from src.domains.agents.application.relation_debrief_read import RelationStoredDebriefQuery
from src.domains.relations.debrief.service import RelationDebriefService


class RelationDebriefBuildRequest(RelationStoredDebriefQuery):
    force: StrictBool = False


class RelationDebriefBuildScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: RelationDebriefBuildRequest
    canonical_key: str
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    debrief_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: str
    language: str
    scope: dict[str, JsonValue]

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "name": self.request.name,
            "force": self.request.force,
            "status": self.status,
            "language": self.language,
            "scope": self.scope,
        }


class RelationDebriefBuildPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    relation_debrief: RelationDebriefBuildScope


if set(signature(RelationDebriefService.build).parameters) != {"self", "name", "force"}:
    raise AssertionError(
        "New source debrief controls require reviewed tool inputs and confirmation"
    )
