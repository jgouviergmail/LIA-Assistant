"""Prepare and execute sparse report changes through the original atomic owner."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_action_budget import require_meeting_action_budget
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_report_update_schemas import (
    ReportUpdateInput,
    ReportUpdatePatch,
    ReportUpdateSelection,
    canonical_report_update,
    report_update_states,
)
from src.domains.agents.application.meeting_report_update_spec import REPORT_UPDATE_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_report_updates import (
    ReportPatchConfirmation,
    ReportPatchState,
    get_meeting_report_updates,
)


async def prepare_report_update(
    db: AsyncSession, actor_id: UUID, request: ReportUpdateInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    actor = await require_meeting_preferences(db, actor_id)
    state = await get_meeting_report_updates().read_update(
        db, actor_id, request.meeting_id, request.changes, actor.language
    )
    try:
        selected = ReportUpdateSelection(request=request, expected=state)
    except ValidationError:
        raise CommandRejected("CONSTRAINT_VIOLATION") from None
    await require_meeting_preferences(db, actor_id)
    draft = build_action_content(
        actor_id,
        REPORT_UPDATE_OPERATION,
        ReportUpdatePatch(meeting_report_update=selected),
        *report_update_states(selected),
        command_id=command_id,
    )
    require_meeting_action_budget(draft)
    return draft


async def execute_report_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_report_update(draft):
        raise ValueError("Report update requires exact selected before/after values")
    selected = ReportUpdatePatch.model_validate(draft.intent).meeting_report_update

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(actual: ReportPatchState) -> None:
        if actual != selected.expected:
            raise ResourceConflictError("meeting_report", detail={"error_code": "STALE_STATE"})

    await check()
    actor = await require_meeting_preferences(db, actor_id)
    confirmation = ReportPatchConfirmation(validate=validate, check=check, receipt=receipt)
    try:
        await get_meeting_report_updates().update(
            db,
            actor_id,
            selected.request.meeting_id,
            selected.request.changes,
            actor.language,
            confirmation,
        )
    except CommitCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
