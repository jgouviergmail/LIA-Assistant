"""Original UI patches must be atomic and preserve concurrently edited fields."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import MeetingPatchRequest
from src.domains.meetings.service import MeetingService
from src.domains.users.models import User
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


def _meeting(actor_id, *, status=MeetingStatus.RECORDING, report=None):
    return Meeting(
        user_id=actor_id,
        status=status,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        template_ref="builtin:default_minutes",
        template_name="Original template",
        report_current=report,
    )


@pytest.mark.parametrize(
    "changes", [{"title": "Unavailable"}, {"participants": []}, {"sections": []}]
)
async def test_refused_report_patch_never_commits_its_template_first(
    async_session: AsyncSession, test_user: User, changes: dict[str, object]
) -> None:
    row = _meeting(test_user.id)
    async_session.add(row)
    await async_session.commit()
    actor_id, identity = test_user.id, row.id
    with pytest.raises(BaseAPIException) as refused:
        await MeetingService(async_session).patch_report(
            actor_id,
            identity,
            MeetingPatchRequest.model_validate(
                {"template_ref": "builtin:daily_standup", **changes}
            ),
            "fr",
        )
    assert refused.value.detail["code"] == "report_not_ready"
    await async_session.rollback()
    await async_session.refresh(row)
    assert row.template_ref == "builtin:default_minutes"


async def test_concurrent_sparse_ui_patches_preserve_both_fields(async_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        actor_id = await _user(seed)
        row = _meeting(
            actor_id,
            status=MeetingStatus.READY,
            report={"title": "Before", "participants": [], "sections": []},
        )
        seed.add(row)
        await seed.commit()
        identity = row.id
    read = asyncio.Event()
    release = asyncio.Event()
    original_read = MeetingRepository.get_for_user
    async with factory() as first, factory() as second:

        async def pause_after_first_read(repo, *args, **kwargs):
            value = await original_read(repo, *args, **kwargs)
            if repo.db is first and not read.is_set():
                read.set()
                await release.wait()
            return value

        with patch.object(MeetingRepository, "get_for_user", pause_after_first_read):
            one = asyncio.create_task(
                MeetingService(first).patch_report(
                    actor_id, identity, MeetingPatchRequest(title="Changed title")
                )
            )
            await asyncio.wait_for(read.wait(), 5)
            two = asyncio.create_task(
                MeetingService(second).patch_report(
                    actor_id,
                    identity,
                    MeetingPatchRequest(participants=[{"label": "S1", "name": "New participant"}]),
                )
            )
            try:
                # Before the fix, the unlocked second writer commits over the first snapshot.
                await asyncio.wait_for(asyncio.shield(two), 0.3)
            except TimeoutError:
                pass
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(one, two), 10)
    async with factory() as verify:
        actual = await MeetingRepository(verify).get_for_user(identity, actor_id)
        assert actual.report_current["title"] == "Changed title"
        assert actual.report_current["participants"][0]["name"] == "New participant"


@pytest.mark.parametrize("fail_write", [False, True])
async def test_template_and_report_share_one_commit(
    async_session: AsyncSession, test_user: User, fail_write: bool
) -> None:
    report = {"title": "Before", "participants": [], "sections": []}
    row = _meeting(test_user.id, status=MeetingStatus.STOPPED, report=report)
    async_session.add(row)
    await async_session.commit()
    actor_id, identity = test_user.id, row.id
    # A failure must happen before the only commit, after both SQL statements.
    real_commit = async_session.commit

    async def commit():
        if fail_write:
            raise OSError("commit not sent")
        await real_commit()

    with patch.object(async_session, "commit", commit):
        if fail_write:
            with pytest.raises(OSError):
                await MeetingService(async_session).patch_report(
                    actor_id,
                    identity,
                    MeetingPatchRequest(template_ref="builtin:daily_standup", title="After"),
                    "fr",
                )
            await async_session.rollback()
        else:
            await MeetingService(async_session).patch_report(
                actor_id,
                identity,
                MeetingPatchRequest(template_ref="builtin:daily_standup", title="After"),
                "fr",
            )
    await async_session.refresh(row)
    assert row.template_ref == (
        "builtin:default_minutes" if fail_write else "builtin:daily_standup"
    )
    assert row.report_current["title"] == ("Before" if fail_write else "After")
