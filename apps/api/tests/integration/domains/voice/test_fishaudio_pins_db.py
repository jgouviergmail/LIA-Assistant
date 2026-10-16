"""The instance's pinned Fish Audio voices, on real PostgreSQL (ADR-345 amendment 2026-10-14).

What only the database can prove:

- the list keeps the order the voices were pinned in, a voice once;
- the published ceiling holds under concurrency: two administrators racing for
  the last slot cannot both land, and two pinning the same voice write one row
  (the read and the write are serialised by an instance-wide advisory lock);
- a pin outlives the administrator who made it (``pinned_by`` becomes NULL).

The store opens its own sessions, so its writes really commit: every test runs
on an emptied table and empties it again, and the accounts it creates are
removed by the committed-accounts fixture.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.users.models import User
from src.domains.voice.fishaudio import pins as module
from src.domains.voice.fishaudio.models import FishAudioPinnedVoice
from src.domains.voice.fishaudio.pins import PinsFull, add_pin, read_pins, remove_pin
from tests.fixtures.factories import UserFactory
from tests.helpers.provider_keys import provider_key_scope

pytestmark = pytest.mark.integration

A = "a" * 32
B = "b" * 32
CREDENTIAL = credential_fingerprint("test-key")


def voice(index: int) -> str:
    return f"{index:032x}"


@pytest_asyncio.fixture
async def factory(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """The store's session door on the test database, around an emptied table."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def committed() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def empty() -> None:
        async with maker() as db:
            await db.execute(delete(FishAudioPinnedVoice))
            await db.commit()

    monkeypatch.setattr(module, "get_db_context", committed)
    await empty()
    async with provider_key_scope(maker, provider="fishaudio", key="test-key"):
        yield maker
    await empty()


@pytest_asyncio.fixture
async def admin(factory: async_sessionmaker[AsyncSession], committed_user_ids: list[UUID]) -> UUID:
    async with factory() as db:
        user = UserFactory.create(is_superuser=True)
        db.add(user)
        await db.flush()
        committed_user_ids.append(user.id)
        await db.commit()
        return user.id


class TestTheList:
    async def test_the_order_is_kept_and_a_voice_pinned_once(self, admin: UUID) -> None:
        assert await add_pin(A, admin, credential_fingerprint=CREDENTIAL) == ((A,), True)
        assert await add_pin(B, admin, credential_fingerprint=CREDENTIAL) == ((A, B), True)
        assert await add_pin(A, admin, credential_fingerprint=CREDENTIAL) == ((A, B), False)

        assert await read_pins() == (A, B)

    async def test_the_ceiling_holds(self, admin: UUID) -> None:
        for index in range(settings.fishaudio_pinned_voices_max):
            await add_pin(voice(index), admin, credential_fingerprint=CREDENTIAL)

        with pytest.raises(PinsFull):
            await add_pin(A, admin, credential_fingerprint=CREDENTIAL)

        assert len(await read_pins()) == settings.fishaudio_pinned_voices_max

    async def test_an_unpin_says_whether_it_unpinned(self, admin: UUID) -> None:
        await add_pin(A, admin, credential_fingerprint=CREDENTIAL)
        await add_pin(B, admin, credential_fingerprint=CREDENTIAL)

        assert await remove_pin(A, admin) == ((B,), True)
        assert await remove_pin(A, admin) == ((B,), False)

    async def test_a_pin_outlives_the_administrator_who_made_it(
        self, factory: async_sessionmaker[AsyncSession], admin: UUID
    ) -> None:
        await add_pin(A, admin, credential_fingerprint=CREDENTIAL)

        async with factory() as db:
            await db.execute(delete(User).where(User.id == admin))
            await db.commit()
            pinned_by = await db.scalar(
                select(FishAudioPinnedVoice.pinned_by).where(FishAudioPinnedVoice.voice_id == A)
            )

        assert await read_pins() == (A,)
        assert pinned_by is None


@pytest_asyncio.fixture
async def administrators(
    admin: UUID,
    factory: async_sessionmaker[AsyncSession],
    committed_user_ids: list[UUID],
) -> tuple[UUID, UUID]:
    async with factory() as db:
        other = UserFactory.create(is_superuser=True)
        db.add(other)
        await db.flush()
        committed_user_ids.append(other.id)
        await db.commit()
        return admin, other.id


class TestUnderConcurrency:
    async def test_two_pins_racing_for_the_last_slot_cannot_both_land(
        self, administrators: tuple[UUID, UUID]
    ) -> None:
        first_admin, second_admin = administrators
        for index in range(settings.fishaudio_pinned_voices_max - 1):
            await add_pin(voice(index), first_admin, credential_fingerprint=CREDENTIAL)

        async def pin(voice_id: str, pinned_by: UUID) -> str:
            try:
                await add_pin(voice_id, pinned_by, credential_fingerprint=CREDENTIAL)
            except PinsFull:
                return "full"
            return "pinned"

        outcomes = await asyncio.gather(pin(A, first_admin), pin(B, second_admin))

        assert sorted(outcomes) == ["full", "pinned"]
        assert len(await read_pins()) == settings.fishaudio_pinned_voices_max

    async def test_two_pins_of_one_voice_write_one_row(
        self, administrators: tuple[UUID, UUID]
    ) -> None:
        first_admin, second_admin = administrators
        outcomes = await asyncio.gather(
            add_pin(A, first_admin, credential_fingerprint=CREDENTIAL),
            add_pin(A, second_admin, credential_fingerprint=CREDENTIAL),
        )

        assert sorted(pinned for _, pinned in outcomes) == [False, True]
        assert await read_pins() == (A,)
