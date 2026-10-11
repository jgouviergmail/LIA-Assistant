"""The original meetings service owns the native transcript purge."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.service import MeetingService
from src.domains.meetings.transcript_confirmation import transcript_state
from src.infrastructure.meeting_transcripts import (
    MeetingTranscriptState,
    TranscriptWriteConfirmation,
)


class SavedMeetingTranscripts:
    async def read(
        self, db: AsyncSession, actor_id: UUID, meeting_id: UUID
    ) -> MeetingTranscriptState:
        return transcript_state(
            await MeetingService(db).transcript_for_deletion(actor_id, meeting_id)
        )

    async def delete(
        self,
        db: AsyncSession,
        actor_id: UUID,
        meeting_id: UUID,
        confirmation: TranscriptWriteConfirmation,
    ) -> None:
        await MeetingService(db).delete_transcript(actor_id, meeting_id, confirmation=confirmation)
