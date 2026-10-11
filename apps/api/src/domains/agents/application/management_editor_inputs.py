"""UI management editing exposes requests only, never frozen quota or state observations."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.asset_editor_inputs import (
    ASSET_EDITOR_MODELS,
    asset_editor_request,
)
from src.domains.agents.application.document_archive_schemas import (
    DocumentArchiveInput,
    DocumentArchivePatch,
)
from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteInput,
    DocumentDeletePatch,
)
from src.domains.agents.application.document_download_schemas import (
    DocumentDownloadInput,
    DocumentDownloadPatch,
)
from src.domains.agents.application.document_move_schemas import (
    DocumentMoveInput,
    DocumentMovePatch,
)
from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadPatch,
)
from src.domains.agents.application.meeting_editor_inputs import (
    MEETING_EDITOR_MODELS,
    meeting_editor_request,
)
from src.domains.agents.application.skill_editor_inputs import (
    SKILL_EDITOR_MODELS,
    skill_editor_request,
)
from src.domains.agents.application.source_editor_inputs import (
    SOURCE_EDITOR_MODELS,
    source_editor_request,
)
from src.domains.agents.application.space_create_schemas import SpaceCreateInput, SpaceCreatePatch
from src.domains.agents.application.space_delete_schemas import SpaceDeleteInput, SpaceDeletePatch
from src.domains.agents.application.space_update_schemas import SpaceUpdateInput, SpaceUpdatePatch
from src.domains.agents.application.workboard_editor_inputs import (
    WORKBOARD_EDITOR_MODELS,
    workboard_editor_request,
)

MANAGEMENT_EDITOR_MODELS: tuple[type[BaseModel], ...] = (
    *MEETING_EDITOR_MODELS,
    *SKILL_EDITOR_MODELS,
    *ASSET_EDITOR_MODELS,
    *SOURCE_EDITOR_MODELS,
    *WORKBOARD_EDITOR_MODELS,
    SpaceCreatePatch,
    SpaceUpdatePatch,
    SpaceDeletePatch,
    DocumentDownloadPatch,
    DocumentUploadPatch,
    DocumentArchivePatch,
    DocumentDeletePatch,
    DocumentMovePatch,
)


def management_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model in MEETING_EDITOR_MODELS:
        return meeting_editor_request(model, intent)
    if model in SKILL_EDITOR_MODELS:
        return skill_editor_request(model, intent)
    if model in ASSET_EDITOR_MODELS:
        return asset_editor_request(model, intent)
    if model in SOURCE_EDITOR_MODELS:
        return source_editor_request(model, intent)
    if model is DocumentUploadPatch:
        selected_upload = DocumentUploadPatch.model_validate(intent).document_to_upload
        return DocumentUploadInput, {"space_id": str(selected_upload.space.id)}
    if model is SpaceCreatePatch:
        creation = SpaceCreatePatch.model_validate(intent).space_create
        return SpaceCreateInput, creation.request.model_dump(mode="json")
    if model is DocumentDownloadPatch:
        selected = DocumentDownloadPatch.model_validate(intent).document_to_download
        return DocumentDownloadInput, {
            "space_id": str(selected.space_id),
            "document_id": str(selected.document_id),
        }
    if model is DocumentArchivePatch:
        archive = DocumentArchivePatch.model_validate(intent).archive_to_download
        return DocumentArchiveInput, {
            "space_id": str(archive.space_id),
            "document_ids": [str(document.document_id) for document in archive.documents],
        }
    if model is SpaceDeletePatch:
        deletion = SpaceDeletePatch.model_validate(intent).space_delete
        return SpaceDeleteInput, deletion.request.model_dump(mode="json")
    if model is DocumentDeletePatch:
        deletion_documents = DocumentDeletePatch.model_validate(intent).documents_to_delete
        return DocumentDeleteInput, deletion_documents.request.model_dump(mode="json")
    if model is DocumentMovePatch:
        movement = DocumentMovePatch.model_validate(intent).documents_to_move
        return DocumentMoveInput, movement.request.model_dump(mode="json")
    if model is SpaceUpdatePatch:
        update = SpaceUpdatePatch.model_validate(intent).space_update
        return SpaceUpdateInput, update.request.model_dump(mode="json", exclude_unset=True)
    return workboard_editor_request(model, intent)
