"""Exact PDF consent uses the original authenticated browser and transfer owner."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.meeting_pdf_schemas import (
    MeetingPDFInput,
    MeetingPDFPatch,
    canonical_meeting_pdf,
)
from src.domains.agents.application.meeting_pdf_spec import MEETING_PDF_OPERATION
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.stored_download_service import (
    Check,
    StoredDownload,
    serve_stored_download_command,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.meeting_pdf import get_meeting_pdf


async def prepare_meeting_pdf(
    db: AsyncSession, actor_id: UUID, request: MeetingPDFInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    actor = await require_meeting_preferences(db, actor_id)
    selected = await get_meeting_pdf().snapshot(db, actor_id, request.meeting_id, actor.language)
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_meeting_preferences(db, actor_id)
    return build_action_content(
        actor_id,
        MEETING_PDF_OPERATION,
        MeetingPDFPatch(meeting_pdf_download=selected),
        {"meeting_pdf_download": None},
        {"meeting_pdf_download": selected.public_scope()},
        command_id=command_id,
    )


async def serve_meeting_pdf_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> StoredFileResponse:
    async def prepare(draft: ApplicationActionDraftContent, check: Check) -> StoredDownload:
        if not canonical_meeting_pdf(draft):
            raise CommandRejected("INVALID_INPUT")
        selected = MeetingPDFPatch.model_validate(draft.intent).meeting_pdf_download
        actor = await require_meeting_preferences(db, actor_id)
        fresh = await get_meeting_pdf().snapshot(db, actor_id, selected.meeting_id, actor.language)
        if fresh != selected:
            raise CommandRejected("STALE_STATE")
        reader = await get_meeting_pdf().render(db, actor_id, selected, check)
        return StoredDownload(
            reader, selected.filename, "application/pdf", {"meeting_id": str(selected.meeting_id)}
        )

    return await serve_stored_download_command(
        db, actor_id, command_id, origin, operation=MEETING_PDF_OPERATION, prepare=prepare
    )
