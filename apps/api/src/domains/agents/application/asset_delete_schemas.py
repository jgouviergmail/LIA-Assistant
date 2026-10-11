"""Destructive generated-file consent seals metadata and each local file identity."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.domains.agents.application.asset_selection_schemas import AssetSelectionInput
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.attachments.schemas import GeneratedAssetsDeleteRequest, GeneratedAssetSummary

ASSET_DELETE_MAX_BYTES = 64_000


class AssetDeleteInput(AssetSelectionInput):
    """Only exact current-account generated ids; no stored path or force flag."""


assert set(AssetDeleteInput.model_fields) == set(GeneratedAssetsDeleteRequest.model_fields)


class AssetDeleteSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: AssetDeleteInput
    items: tuple[GeneratedAssetSummary, ...]
    files: tuple[AssetFileWitness, ...] = Field(repr=False)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "items": [item.model_dump(mode="json") for item in self.items],
            "deletion_requested": after,
            "deleted": len(self.items) if after else 0,
        }


class AssetDeletePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assets_to_delete: AssetDeleteSelection


class AssetDeleteField(StrEnum):
    DELETE = "assets_to_delete"


def canonical_asset_deletion(draft: ApplicationActionDraftContent) -> bool:
    selected = AssetDeletePatch.model_validate(draft.intent).assets_to_delete
    return draft.before == {"assets_to_delete": selected.public_scope()} and draft.after == {
        "assets_to_delete": selected.public_scope(after=True)
    }
