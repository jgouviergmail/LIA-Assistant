"""Independent workers cannot duplicate or overwrite a newer meeting rebuild."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStage, MeetingStatus
from src.domains.meetings.regeneration import regenerate_minutes
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import MeetingReport, TemplateSelection
from src.domains.meetings.synthesis import SynthesisResult, SynthesisUsage
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.template_resolution import TemplateDecision
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["valid", "duplicate", "stale", "cancelled"])
async def test_regeneration_workers_have_independent_fenced_sessions(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    committed_user_ids: list[UUID],
) -> None:
    monkeypatch.setattr(settings, "meetings_job_heartbeat_interval_seconds", 0.02)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        actor = await _user(seed)
        committed_user_ids.append(actor)
        row = Meeting(
            user_id=actor,
            status=MeetingStatus.READY,
            stage=MeetingStage.SYNTHESIZING,
            started_at=datetime.now(UTC),
            audio_format=MeetingAudioFormat.WEBM_OPUS,
            client_timezone="UTC",
            transcript_encrypted=encrypt_data(
                '[{"speaker":"S1","start":0,"end":1,"text":"Private"}]'
            ),
            report_current={"title": "Original", "participants": [], "sections": []},
        )
        seed.add(row)
        await seed.commit()
        identity = row.id

    @asynccontextmanager
    async def database():
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    entered, release, aborted = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def model(*args, **kwargs):
        entered.set()
        try:
            await release.wait()
            return SynthesisResult(
                MeetingReport(title="Current"), SynthesisUsage(0, 0, 0, "controlled"), False
            )
        except asyncio.CancelledError:
            aborted.set()
            raise

    template = TemplateDecision(
        sections=[],
        ref=TemplateRef.builtin("default_minutes"),
        name="Default",
        selection=TemplateSelection.PREFERENCE,
        reason=None,
    )
    with (
        patch("src.domains.meetings.regeneration.get_db_context", database),
        patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            AsyncMock(return_value=SimpleNamespace(allowed=True)),
        ) as quota,
        patch(
            "src.domains.meetings.regeneration.template_for_regeneration",
            AsyncMock(return_value=template),
        ),
        patch(
            "src.domains.meetings.regeneration.synthesize_minutes", side_effect=model
        ) as synthesize,
        patch("src.domains.meetings.regeneration.bill_captured_usage", AsyncMock()),
        patch("src.infrastructure.proactive.tracking.bill_captured_usage", AsyncMock()),
        patch("src.domains.meetings.indexing.schedule_reindex") as index,
    ):
        job = asyncio.create_task(regenerate_minutes(identity))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if scenario == "duplicate":
                await regenerate_minutes(identity)
                assert synthesize.call_count == 1 and quota.await_count == 1
            if scenario == "stale":
                async with factory() as second:
                    await second.execute(
                        update(Meeting)
                        .where(Meeting.id == identity)
                        .values(heartbeat_at=datetime.now(UTC) - timedelta(hours=24))
                    )
                    await second.commit()
                    repo = MeetingRepository(second)
                    assert (
                        await repo.clear_stale_regenerations(
                            settings.meetings_job_lease_ttl_seconds
                        )
                        >= 1
                    )
                    assert await repo.begin_regenerate(identity)
                    assert await repo.claim_regeneration(
                        identity,
                        worker_id="new-owner",
                        ttl_seconds=settings.meetings_job_lease_ttl_seconds,
                    )
                await asyncio.wait_for(aborted.wait(), 5)
            elif scenario == "cancelled":
                job.cancel()
            else:
                release.set()
            if scenario == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(job, 5)
            else:
                await asyncio.wait_for(job, 5)
        finally:
            release.set()
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)
        async with factory() as verify:
            actual = await MeetingRepository(verify).get_by_id(identity)
            if scenario in {"valid", "duplicate"}:
                assert actual.report_current["title"] == "Current"
                assert actual.stage is None and actual.worker_id is None
                index.assert_called_once_with(identity)
            else:
                assert actual.report_current["title"] == "Original"
                index.assert_not_called()
                assert aborted.is_set()
                if scenario == "stale":
                    assert (
                        actual.stage is MeetingStage.SYNTHESIZING
                        and actual.worker_id == "new-owner"
                    )
                else:
                    assert actual.stage is None and actual.worker_id is None
