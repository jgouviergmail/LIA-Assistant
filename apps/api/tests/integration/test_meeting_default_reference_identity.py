"""Equivalent UUID spellings must not leave a deleted default template selected."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.preference_commands import replace_meeting_preferences
from src.domains.meetings.repository import MeetingPreferenceRepository
from src.domains.meetings.schemas import (
    MeetingPreferencesUpdate,
    MeetingTemplateCreate,
    TemplateSection,
)
from src.domains.meetings.template_gateway import SavedMeetingTemplates
from src.domains.meetings.template_service import MeetingTemplateService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("legacy", [False, True])
async def test_uppercase_owned_reference_is_canonical_and_deleted_default_is_cleared(
    async_session: AsyncSession, test_user: User, legacy: bool
) -> None:
    service = MeetingTemplateService(async_session)
    template = await service.create(
        test_user.id,
        MeetingTemplateCreate(
            name="Controlled",
            sections=[
                TemplateSection(
                    key="summary", label="Summary", instruction="Literal", kind="paragraph"
                )
            ],
        ),
        "fr",
    )
    uppercase = "user:" + str(template.id).upper()
    saved = await replace_meeting_preferences(
        async_session,
        test_user.id,
        MeetingPreferencesUpdate(
            stt_engine="auto",
            language="auto",
            auto_email=False,
            keep_audio_hours=0,
            default_template_ref=uppercase,
        ),
        "fr",
    )
    assert saved.default_template_ref == template.ref
    if legacy:
        row = await MeetingPreferenceRepository(async_session).get_for_user(test_user.id)
        assert row is not None
        row.default_template_ref = uppercase
        await async_session.commit()
    assert await SavedMeetingTemplates().default_ref(async_session, test_user.id) == template.ref
    assert await service.delete(test_user.id, template.ref) is True
    row = await MeetingPreferenceRepository(async_session).get_for_user(test_user.id)
    assert row is not None and row.default_template_ref is None
