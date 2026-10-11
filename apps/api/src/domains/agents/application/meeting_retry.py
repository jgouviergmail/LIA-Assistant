"""Requeue only the full source the person just confirmed."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_retry_schemas import (
    MeetingRetryInput,
    MeetingRetryPatch,
    canonical_meeting_retry,
    retry_states,
)
from src.domains.agents.application.meeting_retry_spec import MEETING_RETRY_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_retry import (
    MeetingRetryConfirmation,
    MeetingRetrySnapshot,
    get_meeting_retry,
)


async def prepare_meeting_retry(
    db: AsyncSession, actor_id: UUID, request: MeetingRetryInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    selected = await get_meeting_retry().snapshot(db, actor_id, request.meeting_id)
    await require_meeting_preferences(db, actor_id)
    return build_action_content(
        actor_id,
        MEETING_RETRY_OPERATION,
        MeetingRetryPatch(meeting_retry=selected),
        *retry_states(selected),
        command_id=command_id,
    )


async def execute_meeting_retry(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_meeting_retry(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = MeetingRetryPatch.model_validate(draft.intent).meeting_retry

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(actual: MeetingRetrySnapshot) -> None:
        if actual != selected:
            raise ResourceConflictError("meeting_retry", detail={"error_code": "STALE_STATE"})

    await check()
    try:
        await get_meeting_retry().retry(
            db,
            actor_id,
            selected.meeting_id,
            MeetingRetryConfirmation(validate=validate, check=check, receipt=receipt),
        )
    except CommitCompletionUnknown:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
