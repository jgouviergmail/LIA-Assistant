"""UI and assistant preferences must share one serial, fresh write owner."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.meetings.models import MeetingPreference
from src.domains.meetings.schemas import MeetingPreferencesResponse, MeetingPreferencesUpdate
from src.domains.meetings.service import MeetingService
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


async def test_concurrent_original_ui_first_writes_create_one_owned_preference(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        committed_user_ids.append(owner)
        await seed.commit()
    ready = asyncio.Barrier(2)

    async def write(language: str) -> MeetingPreferencesResponse:
        async with factory() as db:
            await ready.wait()
            return await MeetingService(db).put_preferences(
                owner,
                MeetingPreferencesUpdate(
                    stt_engine="auto",
                    language=language,
                    auto_email=False,
                    keep_audio_hours=0,
                ),
            )

    results = await asyncio.gather(write("en"), write("fr"), return_exceptions=True)
    assert all(not isinstance(value, BaseException) for value in results), [
        (type(value).__name__, str(getattr(value, "orig", ""))[:180]) for value in results
    ]
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MeetingPreference)
                .where(MeetingPreference.user_id == owner)
            )
            == 1
        )
