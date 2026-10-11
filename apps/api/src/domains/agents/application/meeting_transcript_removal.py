"""Fresh exact HITL delegates to the original transcript purge owner."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_transcript_schemas import (
    TranscriptDeleteInput,
    TranscriptDeletePatch,
    TranscriptDeleteSelection,
    canonical_transcript_deletion,
    transcript_deletion_states,
)
from src.domains.agents.application.meeting_transcript_spec import TRANSCRIPT_DELETE_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_transcripts import (
    MeetingTranscriptState,
    TranscriptWriteConfirmation,
    get_meeting_transcripts,
)


async def prepare_transcript_deletion(
    db: AsyncSession,
    actor_id: UUID,
    request: TranscriptDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    expected = await get_meeting_transcripts().read(db, actor_id, request.meeting_id)
    await require_meeting_preferences(db, actor_id)
    selected = TranscriptDeleteSelection(request=request, expected=expected)
    return build_action_content(
        actor_id,
        TRANSCRIPT_DELETE_OPERATION,
        TranscriptDeletePatch(meeting_transcript_delete=selected),
        *transcript_deletion_states(selected),
        command_id=command_id,
    )


async def execute_transcript_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_transcript_deletion(draft):
        raise ValueError("Transcript deletion requires the exact confirmed scope")
    selected = TranscriptDeletePatch.model_validate(draft.intent).meeting_transcript_delete

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(state: MeetingTranscriptState) -> None:
        if state != selected.expected:
            raise ResourceConflictError("meeting_transcript", detail={"error_code": "STALE_STATE"})

    await check()
    confirmation = TranscriptWriteConfirmation(validate=validate, check=check, receipt=receipt)
    try:
        await get_meeting_transcripts().delete(
            db, actor_id, selected.request.meeting_id, confirmation
        )
    except CommitCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
