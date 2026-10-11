"""Only an exact optional plugin target enters the model-visible browser upload request."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_package_models import PluginImportState
from src.domains.agents.application.plugin_read_schemas import PluginReadItem


class PluginFileUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    replace_plugin_id: UUID | None = None


class PluginFileUploadSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PluginFileUploadInput
    previous: PluginReadItem | None
    state: PluginImportState | None = Field(repr=False)
    max_file_size_bytes: StrictInt = Field(ge=1)
    max_package_files: StrictInt = Field(ge=1)
    max_decompressed_bytes: StrictInt = Field(ge=1)
    max_personal_plugins: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def exact_replacement(self) -> PluginFileUploadSelection:
        if self.previous is None:
            if self.request.replace_plugin_id is not None or self.state is not None:
                raise ValueError("A new plugin cannot carry a replacement witness")
        elif (
            self.request.replace_plugin_id != self.previous.id
            or self.state is None
            or self.state.previous != self.previous
        ):
            raise ValueError("Replacement identity, metadata and witness must agree")
        return self

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            **self.model_dump(mode="json", exclude={"state"}),
            "allowed_extensions": [".zip"],
            "browser_file_confirmation_required": True,
        }


class PluginFileUploadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plugin_file_upload: PluginFileUploadSelection


class PluginFileUploadField(StrEnum):
    UPLOAD = "plugin_file_upload"


def canonical_plugin_file_upload(draft: ApplicationActionDraftContent) -> bool:
    selected = PluginFileUploadPatch.model_validate(draft.intent).plugin_file_upload
    return draft.before == {
        "plugin_file_upload": (
            selected.previous.model_dump(mode="json") if selected.previous else None
        )
    } and draft.after == {"plugin_file_upload": selected.public_scope()}
