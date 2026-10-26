"""Real SQL fences duplicate, parallel and uncertain paid message attempts."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.users.models import User
from src.domains.world.message_attempts import AttemptBusy, AttemptConflict, MessageAttempts

pytestmark = pytest.mark.integration


async def accounts(engine: AsyncEngine, owned: list[UUID], count: int = 3) -> list[UUID]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        people = [
            User(email=f"message-{uuid4().hex}@example.invalid", is_active=True)
            for _ in range(count)
        ]
        db.add_all(people)
        await db.flush()
        identities = [person.id for person in people]
        owned.extend(identities)
        await db.commit()
        return identities


async def test_duplicate_claims_and_changed_payloads_never_buy_another_attempt(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    sender, recipient, _ = await accounts(async_engine, committed_user_ids)
    repo = MessageAttempts("test-" + uuid4().hex)
    message = uuid4()
    now = datetime.now(UTC)
    outcomes = await asyncio.gather(
        *[
            repo.enqueue(message, sender, recipient, "a" * 64, translated=True, now=now)
            for _ in range(8)
        ]
    )
    assert sum(created for _, created in outcomes) == 1
    assert len({row.token for row, _ in outcomes}) == 1
    with pytest.raises(AttemptConflict):
        await repo.enqueue(message, sender, recipient, "b" * 64, translated=True, now=now)
    row = outcomes[0][0]
    assert not await repo.start(message, row.token, now=now)
    assert await repo.mark_ready(message, row.token, now=now)
    assert await repo.start(message, row.token, now=now)
    assert not await repo.start(message, row.token, now=now)
    assert await repo.finish(message, row.token, "succeeded", now=now)
    assert not await repo.finish(message, uuid4(), "failed", now=now)
    assert not await repo.start(message, row.token, now=now + timedelta(minutes=1))


async def test_paid_capacity_is_fair_bounded_and_never_reclaims_a_started_call(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    people = await accounts(async_engine, committed_user_ids, 6)
    repo = MessageAttempts("test-" + uuid4().hex)
    now = datetime.now(UTC)
    rows = []
    for index in range(5):
        row, created = await repo.enqueue(
            uuid4(),
            people[index],
            people[5],
            str(index) * 64,
            translated=True,
            now=now + timedelta(milliseconds=index),
        )
        assert created
        rows.append(row)
        assert await repo.mark_ready(row.id, row.token, now=now)
    with pytest.raises(AttemptBusy):
        await repo.enqueue(uuid4(), people[0], people[5], "f" * 64, translated=True, now=now)
    assert not await repo.start(rows[2].id, rows[2].token, now=now + timedelta(seconds=1))
    assert await repo.start(rows[0].id, rows[0].token, now=now + timedelta(seconds=1))
    assert await repo.start(rows[1].id, rows[1].token, now=now + timedelta(seconds=1))
    assert not await repo.start(rows[2].id, rows[2].token, now=now + timedelta(seconds=1))
    assert await repo.finish(rows[0].id, rows[0].token, "failed", now=now + timedelta(seconds=2))
    assert await repo.start(rows[2].id, rows[2].token, now=now + timedelta(seconds=2))
    # A worker may die after its provider started: expiry does not grant a retry.
    assert not await repo.start(rows[1].id, rows[1].token, now=now + timedelta(seconds=60))
    assert not await repo.finish(
        rows[1].id, rows[1].token, "succeeded", now=now + timedelta(seconds=60)
    )
    assert not await repo.start(rows[3].id, rows[3].token, now=now + timedelta(seconds=60))


async def test_same_language_needs_no_paid_slot_and_metadata_has_no_body_columns(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    from src.domains.world.message_models import WorldMessageAttempt

    sender, recipient, _ = await accounts(async_engine, committed_user_ids)
    repo = MessageAttempts("test-" + uuid4().hex)
    row, created = await repo.enqueue(
        uuid4(), sender, recipient, "a" * 64, translated=False, now=datetime.now(UTC)
    )
    assert created and row.status == "reserved" and not row.content_ready
    assert await repo.mark_ready(row.id, row.token, now=datetime.now(UTC))
    assert await repo.status(row.id, row.token, now=datetime.now(UTC)) == "delivered"
    assert not {"text", "body", "translation", "cookie", "session_id"} & set(
        WorldMessageAttempt.__table__.columns.keys()
    )


@pytest.mark.parametrize("started", [False, True])
async def test_status_becomes_uncertain_at_the_deadline_without_new_world_activity(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], started: bool
) -> None:
    sender, recipient, outsider = await accounts(async_engine, committed_user_ids)
    repo = MessageAttempts("test-" + uuid4().hex)
    now = datetime.now(UTC)
    row, _ = await repo.enqueue(uuid4(), sender, recipient, "a" * 64, translated=True, now=now)
    assert await repo.mark_ready(row.id, row.token, now=now)
    if started:
        assert await repo.start(row.id, row.token, now=now)
    assert await repo.owned_status(row.id, outsider, now=now) is None
    assert await repo.owned_status(row.id, sender, now=now) == "pending"
    assert await repo.owned_status(row.id, sender, now=now + timedelta(minutes=1)) == "uncertain"


async def test_expired_fences_are_collected_after_a_scene_or_namespace_is_retired(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    from sqlalchemy import update

    from src.domains.world.message_models import WorldMessageAttempt

    sender, recipient, _ = await accounts(async_engine, committed_user_ids)
    now = datetime.now(UTC)
    retired = MessageAttempts("retired-" + uuid4().hex)
    active = MessageAttempts("active-" + uuid4().hex)
    old, _ = await retired.enqueue(uuid4(), sender, recipient, "a" * 64, translated=False, now=now)
    retained, _ = await retired.enqueue(
        uuid4(), sender, recipient, "b" * 64, translated=False, now=now
    )
    async with async_sessionmaker(async_engine)() as db:
        await db.execute(
            update(WorldMessageAttempt)
            .where(WorldMessageAttempt.id == old.id)
            .values(expires_at=now - timedelta(seconds=1))
        )
        await db.commit()
    created, _ = await active.enqueue(
        uuid4(), sender, recipient, "c" * 64, translated=False, now=now
    )
    async with async_sessionmaker(async_engine)() as db:
        assert await db.get(WorldMessageAttempt, old.id) is None
        assert await db.get(WorldMessageAttempt, retained.id) is not None
        assert await db.get(WorldMessageAttempt, created.id) is not None
