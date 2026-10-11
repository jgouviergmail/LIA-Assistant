"""One public plugin source and complete owned replacement seal private package/state hashes."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, field_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_package_models import PluginImportState
from src.domains.agents.application.skill_url_import_schemas import SkillUrlImportInput
from src.domains.plugins.package_preview import PluginPackagePreview


class PluginUrlImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    url: str = Field(min_length=12, max_length=2048, pattern=r"^https://")
    replace_plugin_id: UUID | None = None

    @field_validator("url")
    @classmethod
    def public_source(cls, value: str) -> str:
        return SkillUrlImportInput(url=value).url


class PluginUrlImportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PluginUrlImportInput
    filename: str
    size_bytes: StrictInt = Field(ge=0)
    package: PluginPackagePreview
    state: PluginImportState = Field(repr=False)
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"package_digest", "state"})


class PluginUrlImportPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plugin_url_import: PluginUrlImportSnapshot


class PluginUrlImportField(StrEnum):
    IMPORT = "plugin_url_import"


def canonical_plugin_url_import(draft: ApplicationActionDraftContent) -> bool:
    selected = PluginUrlImportPatch.model_validate(draft.intent).plugin_url_import
    return draft.before == {
        "plugin_url_import": (
            selected.state.previous.model_dump(mode="json") if selected.state.previous else None
        )
    } and draft.after == {"plugin_url_import": selected.public_scope()}
