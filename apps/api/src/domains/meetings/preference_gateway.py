"""Typed preferences port delegates to the exact original UI transaction owner."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.preference_commands import (
    preference_response,
    replace_meeting_preferences,
)
from src.domains.meetings.repository import MeetingPreferenceRepository
from src.domains.meetings.schemas import MeetingPreferencesUpdate
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_preferences import (
    MeetingPreferenceCheck,
    MeetingPreferenceState,
    MeetingPreferenceValues,
)


class SavedMeetingPreferences:
    async def read(self, db: AsyncSession, actor_id: UUID) -> MeetingPreferenceState:
        row = await MeetingPreferenceRepository(db).get_for_user(actor_id)
        return MeetingPreferenceState.model_validate(
            preference_response(row).model_dump(mode="json")
        )

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: MeetingPreferenceValues,
        *,
        expected: MeetingPreferenceState,
        receipt: PreferenceWriteReceipt,
        check: MeetingPreferenceCheck,
    ) -> None:
        await replace_meeting_preferences(
            db,
            actor_id,
            MeetingPreferencesUpdate.model_validate(values.model_dump()),
            None,
            expected=expected,
            receipt=receipt,
            check=check,
        )
