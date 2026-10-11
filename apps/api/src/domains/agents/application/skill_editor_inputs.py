"""Skill editors offer requests only and keep all observed witnesses server-owned."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.skill_delete_schemas import SkillDeleteInput, SkillDeletePatch
from src.domains.agents.application.skill_download_schemas import (
    SkillDownloadInput,
    SkillDownloadPatch,
)
from src.domains.agents.application.skill_file_upload_schemas import (
    SkillFileUploadInput,
    SkillFileUploadPatch,
)
from src.domains.agents.application.skill_library_import_schemas import LibraryImportPatch
from src.domains.agents.application.skill_update_schemas import SkillUpdateInput, SkillUpdatePatch
from src.domains.agents.application.skill_url_import_schemas import (
    SkillUrlImportInput,
    SkillUrlImportPatch,
)

SKILL_EDITOR_MODELS: tuple[type[BaseModel], ...] = (
    SkillDeletePatch,
    SkillFileUploadPatch,
    SkillDownloadPatch,
    SkillUpdatePatch,
    SkillUrlImportPatch,
    LibraryImportPatch,
)


def skill_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is SkillFileUploadPatch:
        file = SkillFileUploadPatch.model_validate(intent).skill_file_upload.request
        return SkillFileUploadInput, file.model_dump(mode="json")
    if model is SkillUrlImportPatch:
        url = SkillUrlImportPatch.model_validate(intent).skill_url_import.request
        return SkillUrlImportInput, url.model_dump(mode="json")
    if model is LibraryImportPatch:
        request = LibraryImportPatch.model_validate(intent).skill_library_import.request
        return type(request), request.model_dump(mode="json")
    if model is SkillDeletePatch:
        removal = SkillDeletePatch.model_validate(intent).skill_to_delete
        return SkillDeleteInput, removal.request.model_dump(mode="json")
    if model is SkillDownloadPatch:
        download = SkillDownloadPatch.model_validate(intent).skill_to_download
        return SkillDownloadInput, download.request.model_dump(mode="json")
    if model is SkillUpdatePatch:
        update = SkillUpdatePatch.model_validate(intent).skill_personal_state
        return SkillUpdateInput, update.request.model_dump(mode="json")
    raise ValueError("Unknown personal skill editor")
