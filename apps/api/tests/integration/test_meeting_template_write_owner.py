"""Template caps and copied names must hold on the original UI write path."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import MeetingTemplate
from src.domains.meetings.repository import MeetingTemplateRepository
from src.domains.meetings.schemas import (
    MeetingTemplateCreate,
    MeetingTemplateUpdate,
    TemplateSection,
)
from src.domains.meetings.template_service import MeetingTemplateService
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


def _request(name: str) -> MeetingTemplateCreate:
    return MeetingTemplateCreate(
        name=name,
        sections=[
            TemplateSection(
                key="summary",
                label="Summary",
                instruction="Summarize the meeting",
                kind="paragraph",
            )
        ],
    )


async def test_concurrent_original_ui_creations_do_not_exceed_the_owned_cap(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, committed_user_ids: list[UUID]
) -> None:
    monkeypatch.setattr(settings, "meetings_max_user_templates", 1)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        actor_id = await _user(seed)
        committed_user_ids.append(actor_id)
        await seed.commit()
    ready = asyncio.Barrier(2)

    async def create(name: str):
        async with factory() as db:
            await ready.wait()
            return await MeetingTemplateService(db).create(actor_id, _request(name), "fr")

    results = await asyncio.gather(create("One"), create("Two"), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    refused = [result for result in results if isinstance(result, BaseAPIException)]
    assert len(refused) == 1 and refused[0].status_code == 409
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MeetingTemplate)
                .where(MeetingTemplate.user_id == actor_id)
            )
            == 1
        )


async def test_copy_of_max_length_name_remains_bounded_and_distinguishable(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        actor_id = await _user(db)
        committed_user_ids.append(actor_id)
        await db.commit()
        service = MeetingTemplateService(db)
        original = await service.create(actor_id, _request("N" * 120), "fr")
        copied = await service.create(
            actor_id, MeetingTemplateCreate(duplicate_of=original.ref), "fr"
        )
        assert copied.name != original.name
        assert len(copied.name) <= 120 and copied.name.endswith(" (2)")


async def test_copy_refreshes_a_previously_loaded_source_after_another_ui_update(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        actor_id = await _user(seed)
        committed_user_ids.append(actor_id)
        await seed.commit()
        source = await MeetingTemplateService(seed).create(actor_id, _request("Original"), "fr")
        assert source.id is not None
        source_id, source_ref = source.id, source.ref
    async with factory() as waiting:
        held = await MeetingTemplateRepository(waiting).get_for_user(source_id, actor_id)
        assert held is not None and held.name == "Original"
        async with factory() as other:
            await MeetingTemplateService(other).update(
                actor_id,
                source_ref,
                MeetingTemplateUpdate(
                    name="Updated",
                    sections=[
                        TemplateSection(
                            key="summary",
                            label="Summary",
                            instruction="Updated instruction",
                            kind="paragraph",
                        )
                    ],
                ),
            )
        copied = await MeetingTemplateService(waiting).create(
            actor_id, MeetingTemplateCreate(duplicate_of=source_ref), "fr"
        )
        assert copied.name.startswith("Updated")
        assert copied.sections[0].instruction == "Updated instruction"
