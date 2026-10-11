"""A blocked account never reaches paid regeneration or changes its minutes."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.meetings.error_codes import ERROR_USAGE_LIMIT
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStage, MeetingStatus
from src.domains.meetings.regeneration import regenerate_minutes
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_blocked_account_preserves_current_minutes_without_a_provider_call(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        stage=MeetingStage.SYNTHESIZING,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted=encrypt_data('[{"speaker":"S1","start":0,"end":1,"text":"Private"}]'),
        report_current={"title": "Original", "participants": [], "sections": []},
    )
    async_session.add(row)
    await async_session.commit()

    @asynccontextmanager
    async def database():
        yield async_session

    with (
        patch("src.domains.meetings.regeneration.get_db_context", database),
        patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            AsyncMock(return_value=SimpleNamespace(allowed=False, blocked_reason="tokens")),
        ) as quota,
        patch("src.domains.meetings.regeneration.synthesize_minutes", AsyncMock()) as model,
        patch(
            "src.domains.meetings.regeneration.template_for_regeneration", AsyncMock()
        ) as template,
    ):
        await regenerate_minutes(row.id)
    quota.assert_awaited_once_with(test_user.id)
    model.assert_not_called()
    template.assert_not_called()
    await async_session.refresh(row)
    assert row.report_current["title"] == "Original"
    assert row.stage is None and row.worker_id is None
    assert row.last_error_code == ERROR_USAGE_LIMIT
