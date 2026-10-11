"""Exact retention consent names owned generated files and current quota/TTL."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt

from src.domains.agents.application.asset_selection_schemas import AssetSelectionInput
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.attachments.schemas import (
    GeneratedAssetKeepUsage,
    GeneratedAssetsKeepRequest,
    GeneratedAssetSummary,
)

ASSET_RETENTION_MAX_BYTES = 64_000


class AssetRetentionInput(AssetSelectionInput):
    kept: StrictBool


assert set(AssetRetentionInput.model_fields) == set(GeneratedAssetsKeepRequest.model_fields)


class AssetRetentionSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: AssetRetentionInput
    items: tuple[GeneratedAssetSummary, ...]
    usage: GeneratedAssetKeepUsage
    ttl_hours: StrictInt = Field(ge=1, le=168)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @property
    def changed_items(self) -> tuple[GeneratedAssetSummary, ...]:
        return tuple(
            item for item in self.items if (item.expires_at is None) is not self.request.kept
        )

    @property
    def desired_usage(self) -> GeneratedAssetKeepUsage:
        sign = 1 if self.request.kept else -1
        return self.usage.model_copy(
            update={
                "kept_files": self.usage.kept_files + sign * len(self.changed_items),
                "kept_bytes": self.usage.kept_bytes
                + sign * sum(item.file_size for item in self.changed_items),
            }
        )

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        usage = (self.desired_usage if after else self.usage).model_dump(mode="json")
        return {
            "items": [
                item.model_dump(mode="json", exclude={"expires_at"} if after else set())
                for item in self.items
            ],
            "kept": self.request.kept if after else None,
            "retention_requested": after,
            "release_ttl_hours": self.ttl_hours,
            "usage": usage,
        }


class AssetRetentionPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_retention: AssetRetentionSelection


class AssetRetentionField(StrEnum):
    RETENTION = "asset_retention"


def canonical_asset_retention(draft: ApplicationActionDraftContent) -> bool:
    selected = AssetRetentionPatch.model_validate(draft.intent).asset_retention
    return draft.before == {"asset_retention": selected.public_scope()} and draft.after == {
        "asset_retention": selected.public_scope(after=True)
    }
