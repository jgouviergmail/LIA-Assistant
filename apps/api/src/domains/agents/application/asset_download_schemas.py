"""One generated-file transfer with public metadata and private storage witnesses."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.attachments.schemas import GeneratedAssetSummary


class AssetDownloadInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_id: UUID


class AssetDownloadSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: AssetDownloadInput
    item: GeneratedAssetSummary
    file: AssetFileWitness = Field(repr=False)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.item.model_dump(mode="json")


class AssetDownloadPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_to_download: AssetDownloadSnapshot


def canonical_asset_download(draft: ApplicationActionDraftContent) -> bool:
    selected = AssetDownloadPatch.model_validate(draft.intent).asset_to_download
    return draft.before == {"asset_to_download": None} and draft.after == {
        "asset_to_download": selected.public_scope()
    }
