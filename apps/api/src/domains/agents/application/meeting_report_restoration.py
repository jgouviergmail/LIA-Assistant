"""Restore the exact generated revision through the original guarded writer."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_report_restore_schemas import (
    ReportRestoreInput,
    ReportRestorePatch,
    ReportRestoreSelection,
    canonical_report_restoration,
    report_restore_states,
    restore_witness,
)
from src.domains.agents.application.meeting_report_restore_spec import REPORT_RESTORE_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.confirmed_commit import CommitCompletionUnknown
from src.infrastructure.meeting_reports import (
    MeetingReportState,
    ReportWriteConfirmation,
    get_meeting_reports,
)


async def prepare_report_restoration(
    db: AsyncSession, actor_id: UUID, request: ReportRestoreInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    await require_meeting_preferences(db, actor_id)
    state = await get_meeting_reports().read_restore(db, actor_id, request.meeting_id)
    selected = ReportRestoreSelection(request=request, expected=restore_witness(state))
    await require_meeting_preferences(db, actor_id)
    return build_action_content(
        actor_id,
        REPORT_RESTORE_OPERATION,
        ReportRestorePatch(meeting_report_restore=selected),
        *report_restore_states(selected),
        command_id=command_id,
    )


async def execute_report_restoration(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_report_restoration(draft):
        raise ValueError("Report restoration requires the exact selected version")
    selected = ReportRestorePatch.model_validate(draft.intent).meeting_report_restore

    async def check() -> None:
        if actor_id != draft.actor_id:
            raise CommandRejected("FORBIDDEN")
        await require_meeting_preferences(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def validate(state: MeetingReportState) -> None:
        if restore_witness(state) != selected.expected:
            raise ResourceConflictError("meeting_report", detail={"error_code": "STALE_STATE"})

    await check()
    confirmation = ReportWriteConfirmation(validate=validate, check=check, receipt=receipt)
    try:
        await get_meeting_reports().restore(db, actor_id, selected.request.meeting_id, confirmation)
    except CommitCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
