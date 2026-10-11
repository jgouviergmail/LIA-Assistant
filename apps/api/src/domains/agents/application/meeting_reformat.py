"""Prepare and execute only the complete original reformat scope just confirmed."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.meeting_reformat import MeetingReformatRequest
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_action_budget import require_meeting_action_budget
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_reformat_schemas import (
    MeetingReformatInput,
    MeetingReformatPatch,
    canonical_meeting_reformat,
    reformat_states,
)
from src.domains.agents.application.meeting_reformat_spec import MEETING_REFORMAT_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_reformat import (
    MeetingReformatConfirmation,
    MeetingReformatSnapshot,
    get_meeting_reformat,
)


async def prepare_meeting_reformat(
    db: AsyncSession,
    actor_id: UUID,
    request: MeetingReformatInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    selected = await get_meeting_reformat().snapshot(
        db,
        actor_id,
        request.meeting_id,
        MeetingReformatRequest(template_ref=request.template_ref, mode=request.mode),
        destination_id=request.meeting_id if request.mode == "replace" else uuid4(),
    )
    await require_meeting_preferences(db, actor_id)
    draft = build_action_content(
        actor_id,
        MEETING_REFORMAT_OPERATION,
        MeetingReformatPatch(meeting_reformat=selected),
        *reformat_states(selected),
        command_id=command_id,
    )
    require_meeting_action_budget(draft)
    return draft


async def execute_meeting_reformat(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_meeting_reformat(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = MeetingReformatPatch.model_validate(draft.intent).meeting_reformat

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(actual: MeetingReformatSnapshot) -> None:
        if actual != selected:
            raise ResourceConflictError("meeting_reformat", detail={"error_code": "STALE_STATE"})

    await check()
    try:
        await get_meeting_reformat().reformat(
            db,
            actor_id,
            selected,
            MeetingReformatConfirmation(
                validate=validate,
                check=check,
                receipt=receipt,
                destination_id=selected.destination_id,
            ),
        )
    except CommitCompletionUnknown:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
