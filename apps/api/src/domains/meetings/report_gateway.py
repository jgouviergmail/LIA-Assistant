"""Restore through the original writer; indexing remains the original background job."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.report_confirmation import report_state
from src.domains.meetings.service import MeetingService
from src.infrastructure.meeting_reports import MeetingReportState, ReportWriteConfirmation


class SavedMeetingReports:
    async def read_restore(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingReportState:
        return report_state(await MeetingService(db).report_for_restoration(actor_id, meeting_id))

    async def restore(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: ReportWriteConfirmation,
    ) -> None:
        try:
            await MeetingService(db).reset_report(actor_id, meeting_id, confirmation=confirmation)
        finally:
            if confirmation.receipt.committed and not confirmation.receipt.no_op:
                from src.domains.meetings.indexing import schedule_reindex

                schedule_reindex(meeting_id)
