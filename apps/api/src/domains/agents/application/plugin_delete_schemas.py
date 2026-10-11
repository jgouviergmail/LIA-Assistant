"""Public complete plugin removal scope seals private row and file witnesses."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_read_schemas import PluginReadItem


class PluginDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plugin_id: UUID


class PluginDeleteSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PluginDeleteInput
    plugin: PluginReadItem
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude={"state_digest"})


class PluginDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plugin_to_delete: PluginDeleteSnapshot


class PluginDeleteField(StrEnum):
    DELETE = "plugin_to_delete"


def canonical_plugin_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = PluginDeletePatch.model_validate(draft.intent).plugin_to_delete
    return draft.before == {"plugin_to_delete": selected.public_scope()} and draft.after == {
        "plugin_to_delete": None
    }
