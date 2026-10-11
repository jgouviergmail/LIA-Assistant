"""Original guarded sparse editing with its existing indexing follow-up."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.meeting_reports import MeetingPatchRequest
from src.domains.meetings.report_patch_confirmation import report_patch_state
from src.domains.meetings.service import MeetingService
from src.infrastructure.meeting_report_updates import ReportPatchConfirmation, ReportPatchState


class SavedMeetingReportUpdates:
    async def read_update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        changes: MeetingPatchRequest,
        language: str | None,
    ) -> ReportPatchState:
        service = MeetingService(db)
        return await report_patch_state(
            service, await service._owned(meeting_id, actor_id), changes, language
        )

    async def update(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        changes: MeetingPatchRequest,
        language: str | None,
        confirmation: ReportPatchConfirmation,
    ) -> None:
        try:
            await MeetingService(db).patch_report(
                actor_id, meeting_id, changes, language, confirmation=confirmation
            )
        finally:
            if confirmation.receipt.committed and not confirmation.receipt.no_op:
                from src.domains.meetings.indexing import schedule_reindex

                schedule_reindex(meeting_id)
