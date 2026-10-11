"""Gallery editing offers requests only; private copy/file/quota witnesses stay server-owned."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.asset_delete_schemas import AssetDeleteInput, AssetDeletePatch
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadInput,
    AssetDownloadPatch,
)
from src.domains.agents.application.asset_retention_schemas import (
    AssetRetentionInput,
    AssetRetentionPatch,
)
from src.domains.agents.application.bookmark_delete_schemas import (
    BookmarkDeleteInput,
    BookmarkDeletePatch,
)
from src.domains.agents.application.bookmark_download_schemas import (
    BookmarkDownloadInput,
    BookmarkDownloadPatch,
)
from src.domains.agents.application.bookmark_keep_schemas import (
    BookmarkKeepInput,
    BookmarkKeepPatch,
)
from src.domains.agents.application.email_share_send_schemas import (
    EmailShareSendInput,
    EmailShareSendPatch,
)

ASSET_EDITOR_MODELS: tuple[type[BaseModel], ...] = (
    AssetDeletePatch,
    AssetDownloadPatch,
    AssetRetentionPatch,
    BookmarkKeepPatch,
    BookmarkDeletePatch,
    EmailShareSendPatch,
    BookmarkDownloadPatch,
)


def asset_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is AssetDeletePatch:
        selected_delete = AssetDeletePatch.model_validate(intent).assets_to_delete
        return AssetDeleteInput, selected_delete.request.model_dump(mode="json")
    if model is AssetDownloadPatch:
        selected_download = AssetDownloadPatch.model_validate(intent).asset_to_download
        return AssetDownloadInput, selected_download.request.model_dump(mode="json")
    if model is AssetRetentionPatch:
        selected_retention = AssetRetentionPatch.model_validate(intent).asset_retention
        return AssetRetentionInput, selected_retention.request.model_dump(mode="json")
    if model is BookmarkKeepPatch:
        selected_keep = BookmarkKeepPatch.model_validate(intent).saved_answer_to_keep
        return BookmarkKeepInput, selected_keep.request.model_dump(mode="json")
    if model is BookmarkDeletePatch:
        selected_remove = BookmarkDeletePatch.model_validate(intent).saved_answer_to_delete
        return BookmarkDeleteInput, selected_remove.request.model_dump(mode="json")
    if model is EmailShareSendPatch:
        selected_send = EmailShareSendPatch.model_validate(intent).email_to_send
        return EmailShareSendInput, selected_send.request.model_dump(mode="json")
    if model is BookmarkDownloadPatch:
        selected_downloaded = BookmarkDownloadPatch.model_validate(intent).saved_answer_to_download
        return BookmarkDownloadInput, selected_downloaded.request.model_dump(mode="json")
    raise ValueError("Unknown gallery editor model")
