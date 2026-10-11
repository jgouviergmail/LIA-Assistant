"""An immutable URL package and exact optional owned replacement are approved together."""

from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, field_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.skills.upload_preview import SkillPackagePreview


class SkillUrlImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    url: str = Field(min_length=12, max_length=2048, pattern=r"^https://")
    replace_skill_id: UUID | None = None

    @field_validator("url")
    @classmethod
    def credential_free_source(cls, value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError("Use a public HTTPS source without embedded credentials")
        return value


class SkillUrlImportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SkillUrlImportInput
    filename: str
    size_bytes: StrictInt = Field(ge=0)
    package: SkillPackagePreview
    previous: SkillReadItem | None
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"package_digest", "state_digest"})


class SkillUrlImportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    skill_url_import: SkillUrlImportSnapshot


class SkillUrlImportField(StrEnum):
    IMPORT = "skill_url_import"


def canonical_skill_url_import(draft: ApplicationActionDraftContent) -> bool:
    snapshot = SkillUrlImportPatch.model_validate(draft.intent).skill_url_import
    return draft.before == {
        "skill_url_import": (
            snapshot.previous.model_dump(mode="json") if snapshot.previous is not None else None
        )
    } and draft.after == {"skill_url_import": snapshot.public_scope()}
