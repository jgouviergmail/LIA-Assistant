"""Rebuild only the full transcript/template source the person just confirmed."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_action_budget import require_meeting_action_budget
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_regeneration_schemas import (
    MeetingRegenerationInput,
    MeetingRegenerationPatch,
    canonical_meeting_regeneration,
    regeneration_states,
)
from src.domains.agents.application.meeting_regeneration_spec import MEETING_REGENERATION_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_regeneration import (
    MeetingRegenerationConfirmation,
    MeetingRegenerationSnapshot,
    get_meeting_regeneration,
)


async def prepare_meeting_regeneration(
    db: AsyncSession,
    actor_id: UUID,
    request: MeetingRegenerationInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    selected = await get_meeting_regeneration().snapshot(db, actor_id, request.meeting_id)
    await require_meeting_preferences(db, actor_id)
    draft = build_action_content(
        actor_id,
        MEETING_REGENERATION_OPERATION,
        MeetingRegenerationPatch(meeting_regeneration=selected),
        *regeneration_states(selected),
        command_id=command_id,
    )
    require_meeting_action_budget(draft)
    return draft


async def execute_meeting_regeneration(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_meeting_regeneration(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = MeetingRegenerationPatch.model_validate(draft.intent).meeting_regeneration

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(actual: MeetingRegenerationSnapshot) -> None:
        if actual != selected:
            raise ResourceConflictError(
                "meeting_regeneration", detail={"error_code": "STALE_STATE"}
            )

    await check()
    try:
        await get_meeting_regeneration().regenerate(
            db,
            actor_id,
            selected.meeting_id,
            MeetingRegenerationConfirmation(validate=validate, check=check, receipt=receipt),
        )
    except CommitCompletionUnknown:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
