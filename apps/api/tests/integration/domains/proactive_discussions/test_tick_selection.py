"""The elected tick draws the owners it can serve now, on real PostgreSQL (F019).

Before, four owners were drawn at random among every enabled one: an owner
outside its discussion hours took one of the batch's places, had its controls
read and its rows locked, and was then refused at the claim.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.models import User
from src.infrastructure.scheduler.proactive_discussions import select_owners

pytestmark = pytest.mark.integration

NOON = datetime(2026, 10, 21, 12, tzinfo=UTC)


async def _owner(
    engine: AsyncEngine,
    committed: list[UUID],
    *,
    enabled: bool = True,
    hours: tuple[int, int] = (9, 20),
) -> UUID:
    identity = uuid4()
    async with AsyncSession(engine) as db:
        db.add(
            User(
                id=identity,
                email=f"tick-{identity}@example.test",
                full_name="Fictional tick owner",
                is_active=True,
                is_verified=True,
                is_superuser=False,
                timezone="UTC",
            )
        )
        await db.flush()
        committed.append(identity)
        await DiscussionRepository(db).update_policy(
            identity,
            DiscussionPolicyPatch(
                enabled=enabled,
                start_hour=hours[0],
                end_hour=hours[1],
                sources=(SourceKey.CALENDAR,),
            ),
            expected_revision=0,
        )
        await db.commit()
    return identity


async def test_the_tick_draws_owners_it_can_serve_and_a_requested_rebuild_first(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    in_hours = await _owner(async_engine, committed_user_ids)
    out_of_hours = await _owner(async_engine, committed_user_ids, hours=(20, 21))
    disabled = await _owner(async_engine, committed_user_ids, enabled=False)
    waiting_rebuild = await _owner(async_engine, committed_user_ids, hours=(20, 21))
    async with AsyncSession(async_engine) as db:
        await ContextRepository(db).request_rebuild(waiting_rebuild, expected_epoch=0, now=NOON)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        owners = await select_owners(db, now=NOON)
    # The person who asked for a rebuild is served first, whatever the hour.
    assert owners == (waiting_rebuild, in_hours)
    assert out_of_hours not in owners and disabled not in owners


async def test_the_tick_serves_as_many_owners_as_the_operator_allows(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    eligible = {await _owner(async_engine, committed_user_ids) for _ in range(3)}
    monkeypatch.setattr(settings, "discussion_tick_owners", 2)
    async with AsyncSession(async_engine) as db:
        owners = await select_owners(db, now=NOON)
    assert len(owners) == 2 and set(owners) <= eligible


async def test_a_paused_owner_waits_for_the_end_of_the_pause(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    from datetime import timedelta

    paused = await _owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        await DiscussionRepository(db).update_policy(
            paused,
            DiscussionPolicyPatch(paused_until=NOON + timedelta(hours=1)),
            expected_revision=1,
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        assert await select_owners(db, now=NOON) == ()
        assert await select_owners(db, now=NOON + timedelta(hours=2)) == (paused,)
