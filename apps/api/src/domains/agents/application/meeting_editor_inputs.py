"""Meeting amendments expose sparse requests only, never quota or source witnesses."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.meeting_deletion_schemas import (
    MeetingDeletionInput,
    MeetingDeletionPatch,
)
from src.domains.agents.application.meeting_email_schemas import (
    MeetingEmailInput,
    MeetingEmailPatch,
)
from src.domains.agents.application.meeting_pdf_schemas import MeetingPDFInput, MeetingPDFPatch
from src.domains.agents.application.meeting_preference_schemas import (
    MeetingPreferenceInput,
    MeetingPreferencePatch,
)
from src.domains.agents.application.meeting_reformat_schemas import (
    MeetingReformatInput,
    MeetingReformatPatch,
)
from src.domains.agents.application.meeting_regeneration_schemas import (
    MeetingRegenerationInput,
    MeetingRegenerationPatch,
)
from src.domains.agents.application.meeting_report_restore_schemas import (
    ReportRestoreInput,
    ReportRestorePatch,
)
from src.domains.agents.application.meeting_report_update_schemas import (
    ReportUpdateInput,
    ReportUpdatePatch,
)
from src.domains.agents.application.meeting_retry_schemas import (
    MeetingRetryInput,
    MeetingRetryPatch,
)
from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreateInput,
    TemplateCreatePatch,
    TemplateDeleteInput,
    TemplateDeletePatch,
    TemplateUpdateInput,
    TemplateUpdatePatch,
)
from src.domains.agents.application.meeting_transcript_schemas import (
    TranscriptDeleteInput,
    TranscriptDeletePatch,
)
from src.domains.agents.application.recording_device_schemas import (
    RecordingDevicePatch,
    RecordingDeviceRequest,
)

MEETING_EDITOR_MODELS = (
    RecordingDevicePatch,
    MeetingDeletionPatch,
    MeetingReformatPatch,
    MeetingRegenerationPatch,
    MeetingRetryPatch,
    MeetingEmailPatch,
    MeetingPDFPatch,
    ReportUpdatePatch,
    ReportRestorePatch,
    TranscriptDeletePatch,
    MeetingPreferencePatch,
    TemplateCreatePatch,
    TemplateUpdatePatch,
    TemplateDeletePatch,
)


def meeting_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is RecordingDevicePatch:
        intent = RecordingDevicePatch.model_validate(intent).device_recording.model_dump(
            mode="json", include={"action"}
        )
        return RecordingDeviceRequest, intent
    if model is MeetingDeletionPatch:
        meeting_removal = MeetingDeletionPatch.model_validate(intent).meeting_delete
        return MeetingDeletionInput, {"meeting_id": str(meeting_removal.meeting_id)}
    if model is MeetingReformatPatch:
        reformat = MeetingReformatPatch.model_validate(intent).meeting_reformat
        return MeetingReformatInput, {
            "meeting_id": str(reformat.source.meeting_id),
            **reformat.request.model_dump(mode="json"),
        }
    if model is MeetingRegenerationPatch:
        regeneration = MeetingRegenerationPatch.model_validate(intent).meeting_regeneration
        return MeetingRegenerationInput, {"meeting_id": str(regeneration.meeting_id)}
    if model is MeetingRetryPatch:
        retry = MeetingRetryPatch.model_validate(intent).meeting_retry
        return MeetingRetryInput, {"meeting_id": str(retry.meeting_id)}
    if model is MeetingEmailPatch:
        selected = MeetingEmailPatch.model_validate(intent).meeting_email_send
        return MeetingEmailInput, {"meeting_id": str(selected.meeting_id)}
    if model is MeetingPDFPatch:
        download = MeetingPDFPatch.model_validate(intent).meeting_pdf_download
        return MeetingPDFInput, {"meeting_id": str(download.meeting_id)}
    if model is ReportUpdatePatch:
        update = ReportUpdatePatch.model_validate(intent).meeting_report_update
        return ReportUpdateInput, update.request.model_dump(mode="json", exclude_unset=True)
    if model is ReportRestorePatch:
        restore = ReportRestorePatch.model_validate(intent).meeting_report_restore
        return ReportRestoreInput, restore.request.model_dump(mode="json")
    if model is TranscriptDeletePatch:
        deletion = TranscriptDeletePatch.model_validate(intent).meeting_transcript_delete
        return TranscriptDeleteInput, deletion.request.model_dump(mode="json")
    if model is MeetingPreferencePatch:
        request = MeetingPreferencePatch.model_validate(intent).meeting_preferences.request
        return MeetingPreferenceInput, request.model_dump(mode="json", exclude_unset=True)
    if model is TemplateCreatePatch:
        creation = TemplateCreatePatch.model_validate(intent).meeting_template_create
        return TemplateCreateInput, creation.request.model_dump(mode="json", exclude_unset=True)
    if model is TemplateUpdatePatch:
        replacement = TemplateUpdatePatch.model_validate(intent).meeting_template_update
        return TemplateUpdateInput, replacement.request.model_dump(mode="json", exclude_unset=True)
    removal = TemplateDeletePatch.model_validate(intent).meeting_template_delete
    return TemplateDeleteInput, removal.request.model_dump(mode="json")
