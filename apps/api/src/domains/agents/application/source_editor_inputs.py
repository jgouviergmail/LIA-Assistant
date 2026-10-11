"""Source-family editing projects only requests, never frozen provider/job witnesses."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.source_delete_schemas import (
    SourceDeleteInput,
    SourceDeletePatch,
)
from src.domains.agents.application.source_link_schemas import SourceLinkInput, SourceLinkPatch
from src.domains.agents.application.source_sync_schemas import SourceSyncInput, SourceSyncPatch
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkPatch,
)

SOURCE_EDITOR_MODELS = (SourceLinkPatch, SourceSyncPatch, SourceDeletePatch, SourceUnlinkPatch)


def source_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is SourceLinkPatch:
        selected = SourceLinkPatch.model_validate(intent).source_to_link
        return SourceLinkInput, selected.request.model_dump(mode="json")
    if model is SourceSyncPatch:
        sync = SourceSyncPatch.model_validate(intent).source_to_sync
        return SourceSyncInput, sync.source.request.model_dump(mode="json")
    if model is SourceDeletePatch:
        deletion = SourceDeletePatch.model_validate(intent).source_to_delete
        return SourceDeleteInput, deletion.source.request.model_dump(mode="json")
    if model is SourceUnlinkPatch:
        unlink = SourceUnlinkPatch.model_validate(intent).source_to_unlink
        return SourceUnlinkInput, unlink.request.model_dump(mode="json")
    raise ValueError("Unknown source editor model")
