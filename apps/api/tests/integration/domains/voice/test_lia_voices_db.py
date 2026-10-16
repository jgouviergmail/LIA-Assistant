"""LIA's voices for one person, stored on real PostgreSQL (ADR-345 amendment 2026-10-14).

What only the database can prove: one provider's voices are replaced by ONE
statement that leaves every other provider's in place — including when two saves
for two providers race, and including the entries an older release kept per
model (they go with their provider's save) — and giving a provider's voices back
to the instance removes its entries, the last one leaving the column NULL. Forgetting a person's
last voice leaves SQL NULL too, never the JSON null the merge would turn into
an array.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import BaseAPIException
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.users.models import User
from src.domains.voice import lia_voices as module
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.fishaudio import catalogue_revision as revision_module
from src.domains.voice.fishaudio.models import FishAudioCatalogueRevision
from src.domains.voice.voices_catalog import VoiceOption
from tests.fixtures.factories import UserFactory
from tests.helpers.provider_keys import provider_key_scope

pytestmark = pytest.mark.integration

FISH = "fishaudio"
EDGE = "edge"
CREDENTIAL = credential_fingerprint("test-key")


@pytest_asyncio.fixture
async def person(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[UUID, async_sessionmaker[AsyncSession]]]:
    """A committed account, and the store's session door on the test database."""
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

    monkeypatch.setattr(module, "get_db_context", committed)
    monkeypatch.setattr(revision_module, "get_db_context", committed)
    async with maker() as db:
        await db.execute(delete(FishAudioCatalogueRevision))
        user = UserFactory.create()
        db.add(user)
        await db.flush()
        committed_user_ids.append(user.id)
        await db.commit()
        try:
            async with provider_key_scope(maker, provider="fishaudio", key="test-key"):
                yield user.id, maker
        finally:
            async with maker() as cleanup:
                await cleanup.execute(delete(FishAudioCatalogueRevision))
                await cleanup.commit()


async def _column(maker: async_sessionmaker[AsyncSession], user_id: UUID) -> object:
    async with maker() as db:
        return await db.scalar(select(User.lia_voices).where(User.id == user_id))


@pytest.mark.parametrize(
    ("stored", "expected", "count"),
    [
        (
            {
                FISH: {"male": "b" * 32, "female": "kept"},
                "bad": ["b" * 32],
                EDGE: {"female": 42, "custom": "kept"},
            },
            {FISH: {"female": "kept"}, EDGE: {"custom": "kept"}},
            1,
        ),
        ("b" * 32, None, 1),
        (["b" * 32], None, 1),
        ({"b" * 32: {"female": "kept"}}, {"b" * 32: {"female": "kept"}}, 0),
        ({FISH: {"male": "prefix-" + "b" * 32}}, {FISH: {"male": "prefix-" + "b" * 32}}, 0),
    ],
    ids=["malformed-entries", "legacy-scalar", "legacy-array", "key-only", "substring-only"],
)
async def test_bulk_forget_keeps_other_strings_and_handles_legacy_shapes(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    stored: object,
    expected: object,
    count: int,
) -> None:
    user_id, maker = person
    async with maker() as setup:
        await setup.execute(update(User).where(User.id == user_id).values(lia_voices=stored))
        await setup.commit()
    assert await module.forget_voice("b" * 32) == count
    assert await _column(maker, user_id) == expected


async def test_forgetting_a_voice_uses_one_update_for_all_affected_accounts(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    user_id, maker = person
    gone = "b" * 32
    expected = {EDGE: {"female": "fr-FR-DeniseNeural"}}
    account_ids = [user_id]
    async with maker() as setup:
        for _ in range(2):
            user = UserFactory.create()
            setup.add(user)
            await setup.flush()
            committed_user_ids.append(user.id)
            account_ids.append(user.id)
        await setup.execute(
            update(User)
            .where(User.id.in_(account_ids))
            .values(lia_voices={FISH: {"male": gone}, **expected})
        )
        await setup.commit()
    writes: list[str] = []

    def record(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if "UPDATE USERS" in statement.upper():
            writes.append(statement)

    event.listen(async_engine.sync_engine, "before_cursor_execute", record)
    try:
        assert await module.forget_voice(gone) == len(account_ids)
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", record)
    for account_id in account_ids:
        assert await _column(maker, account_id) == expected
    assert len(writes) == 1, "forgetting a voice must not issue one UPDATE per account"


async def test_forgetting_after_a_concurrent_other_engine_write_keeps_that_write(
    person: tuple[UUID, async_sessionmaker[AsyncSession]], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, maker = person
    gone = "b" * 32
    await module._write(user_id, FISH, {"male": gone}, credential_fingerprint=CREDENTIAL)
    acquired = asyncio.Event()
    deletion_pid: list[int] = []

    @asynccontextmanager
    async def observed() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            deletion_pid.append(await db.scalar(text("SELECT pg_backend_pid()")))
            acquired.set()
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    monkeypatch.setattr(module, "get_db_context", observed)
    async with maker() as writer:
        await writer.execute(
            update(User)
            .where(User.id == user_id)
            .values(lia_voices={FISH: {"male": gone}, EDGE: {"female": "new-concurrent-choice"}})
        )
        forgetting = asyncio.create_task(module.forget_voice(gone))
        try:
            await asyncio.wait_for(acquired.wait(), timeout=5)

            async def wait_for_row_wait() -> None:
                async with maker() as monitor:
                    while not await monitor.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"
                        ),
                        {"pid": deletion_pid[0]},
                    ):
                        await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_row_wait(), timeout=5)
            await writer.commit()
            assert await asyncio.wait_for(forgetting, timeout=5) == 1
        finally:
            await writer.rollback()
            if not forgetting.done():
                forgetting.cancel()
            await asyncio.gather(forgetting, return_exceptions=True)
    assert await _column(maker, user_id) == {EDGE: {"female": "new-concurrent-choice"}}


@pytest.mark.parametrize("already_chosen", [False, True])
async def test_a_selection_validated_before_voice_deletion_cannot_restore_it_afterwards(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
    already_chosen: bool,
) -> None:
    user_id, maker = person
    voice_id = "d" * 32
    offered = EngineVoices(
        TTSConfig(
            provider="fishaudio", model="s2.1-pro", voice_male="default", voice_female="default"
        ),
        [VoiceOption(voice_id, "Proof voice", "male", "fr")],
        multilingual=True,
        credential_fingerprint=CREDENTIAL,
    )
    if already_chosen:
        await module._write(user_id, FISH, {"male": voice_id}, credential_fingerprint=CREDENTIAL)
    validated = asyncio.Event()
    resume = asyncio.Event()
    original_write = module._write

    async def engine() -> EngineVoices:
        return offered

    async def delayed_write(*args: object, **kwargs: object) -> None:
        validated.set()
        await resume.wait()
        await original_write(*args, **kwargs)

    monkeypatch.setattr(module, "chat_engine", engine)
    monkeypatch.setattr(module, "_write", delayed_write)
    selecting = asyncio.create_task(module.save_lia_voices(user_id, "fr", {"male": voice_id}))
    try:
        await asyncio.wait_for(validated.wait(), timeout=5)
        await module.forget_voice(voice_id)
        assert await _column(maker, user_id) is None
        resume.set()
        with pytest.raises(BaseAPIException) as refused:
            await asyncio.wait_for(selecting, timeout=5)
        assert refused.value.status_code in {409, 422, 503}
        assert await _column(maker, user_id) is None
    finally:
        resume.set()
        if not selecting.done():
            selecting.cancel()
        await asyncio.gather(selecting, return_exceptions=True)


@pytest.mark.parametrize("revocation", ["inactive", "deleted", "missing"])
@pytest.mark.parametrize("choice", [{"male": "new-choice"}, {}], ids=["save", "reset"])
async def test_a_preference_write_cannot_reenter_a_revoked_account(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    revocation: str,
    choice: dict[str, str],
) -> None:
    user_id, maker = person
    await module._write(user_id, FISH, {"male": "original"}, credential_fingerprint=CREDENTIAL)
    async with maker() as admin:
        if revocation == "missing":
            await admin.execute(delete(User).where(User.id == user_id))
        else:
            values = (
                {"is_active": False}
                if revocation == "inactive"
                else {"deleted_at": datetime.now(UTC)}
            )
            await admin.execute(update(User).where(User.id == user_id).values(**values))
        await admin.commit()

    with pytest.raises(BaseAPIException) as refused:
        await module._write(user_id, FISH, choice, credential_fingerprint=CREDENTIAL)
    assert refused.value.status_code == 403
    assert await _column(maker, user_id) == (
        None if revocation == "missing" else {FISH: {"male": "original"}}
    )


async def test_each_engine_keeps_its_voices_and_one_is_replaced_whole(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
) -> None:
    user_id, maker = person

    await module._write(
        user_id, FISH, {"male": "m1", "female": "f1"}, credential_fingerprint=CREDENTIAL
    )
    await module._write(
        user_id, EDGE, {"female": "fr-FR-DeniseNeural"}, credential_fingerprint=CREDENTIAL
    )
    await module._write(user_id, FISH, {"female": "f2"}, credential_fingerprint=CREDENTIAL)

    assert await _column(maker, user_id) == {
        FISH: {"female": "f2"},
        EDGE: {"female": "fr-FR-DeniseNeural"},
    }
    assert await module._stored(user_id) == await _column(maker, user_id)


async def test_an_engine_given_back_leaves_no_entry_and_the_last_leaves_null(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
) -> None:
    user_id, maker = person
    await module._write(user_id, FISH, {"male": "m1"}, credential_fingerprint=CREDENTIAL)
    await module._write(
        user_id, EDGE, {"male": "fr-FR-HenriNeural"}, credential_fingerprint=CREDENTIAL
    )

    await module._write(user_id, FISH, {}, credential_fingerprint=CREDENTIAL)
    assert await _column(maker, user_id) == {EDGE: {"male": "fr-FR-HenriNeural"}}

    await module._write(user_id, EDGE, {}, credential_fingerprint=CREDENTIAL)
    assert await _column(maker, user_id) is None


async def test_two_saves_for_two_engines_racing_both_land(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
) -> None:
    user_id, maker = person

    await asyncio.gather(
        module._write(user_id, FISH, {"male": "m1"}, credential_fingerprint=CREDENTIAL),
        module._write(
            user_id, EDGE, {"female": "fr-FR-DeniseNeural"}, credential_fingerprint=CREDENTIAL
        ),
    )

    assert await _column(maker, user_id) == {
        FISH: {"male": "m1"},
        EDGE: {"female": "fr-FR-DeniseNeural"},
    }


async def test_a_deleted_voice_is_forgotten_by_those_who_chose_it_alone(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    committed_user_ids: list[UUID],
) -> None:
    user_id, maker = person
    async with maker() as db:
        neighbour = UserFactory.create()
        db.add(neighbour)
        await db.flush()
        committed_user_ids.append(neighbour.id)
        await db.commit()
    gone = "gone_voice%"  # LIKE's metacharacters must be read as text
    await module._write(
        user_id, FISH, {"male": gone, "female": "f1"}, credential_fingerprint=CREDENTIAL
    )
    await module._write(user_id, EDGE, {"female": gone}, credential_fingerprint=CREDENTIAL)
    # A longer id that merely starts like it, and an account that never chose it.
    await module._write(
        neighbour.id, FISH, {"male": f"{gone}-2"}, credential_fingerprint=CREDENTIAL
    )

    assert await module.forget_voice(gone) == 1

    assert await _column(maker, user_id) == {FISH: {"female": "f1"}}
    assert await _column(maker, neighbour.id) == {FISH: {"male": f"{gone}-2"}}
    assert await module.forget_voice(gone) == 0


async def test_a_person_whose_only_voice_is_deleted_can_choose_again(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, maker = person
    await module._write(user_id, FISH, {"male": "only_voice"}, credential_fingerprint=CREDENTIAL)

    assert await module.forget_voice("only_voice") == 1

    # SQL NULL, never the JSON null: the atomic merge would turn a JSON null into
    # an array, and the removal of an engine would fail on it.
    async with maker() as db:
        unset = await db.scalar(
            text("SELECT lia_voices IS NULL FROM users WHERE id = :id"), {"id": user_id}
        )
    assert unset is True

    async def fresh_engine() -> EngineVoices:
        return EngineVoices(
            TTSConfig(
                provider="fishaudio", model="s2.1-pro", voice_male="default", voice_female="default"
            ),
            [VoiceOption("f1", "Fresh choice", "female", "fr")],
            multilingual=True,
            catalogue_revision=await revision_module.catalogue_revision(),
            credential_fingerprint=CREDENTIAL,
        )

    monkeypatch.setattr(module, "chat_engine", fresh_engine)
    chosen = await module.save_lia_voices(user_id, "fr", {"female": "f1"})
    assert chosen.chosen == {"female": "f1"}
    await module._write(
        user_id, EDGE, {"male": "fr-FR-HenriNeural"}, credential_fingerprint=CREDENTIAL
    )
    await module._write(user_id, EDGE, {}, credential_fingerprint=CREDENTIAL)
    assert await _column(maker, user_id) == {FISH: {"female": "f1"}}


async def test_a_save_replaces_the_entries_an_older_release_kept_per_model(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
    committed_user_ids: list[UUID],
) -> None:
    """2026-10-16: kept per provider AND model before, so a model change of the chat's slot
    gave the person the instance's voices back. A provider's save replaces its entries in
    its one statement; another provider's — older ones included — wait for that one's, and
    nothing of another account's row leaks into it (the subquery reads the row it updates)."""
    user_id, maker = person
    neighbours = {"openai/tts-1": {"male": "echo"}, "gemini": {"female": "Kore"}}
    async with maker() as setup:
        neighbour = UserFactory.create()
        setup.add(neighbour)
        await setup.flush()
        committed_user_ids.append(neighbour.id)
        await setup.execute(
            update(User).where(User.id == neighbour.id).values(lia_voices=neighbours)
        )
        await setup.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                lia_voices={
                    "fishaudio/s2.1-pro": {"male": "m-old"},
                    "fishaudio/s1": {"female": "f-old"},
                    "edge/edge-tts": {"female": "fr-FR-DeniseNeural"},
                }
            )
        )
        await setup.commit()

    await module._write(user_id, FISH, {"male": "m-new"}, credential_fingerprint=CREDENTIAL)
    assert await _column(maker, user_id) == {
        FISH: {"male": "m-new"},
        "edge/edge-tts": {"female": "fr-FR-DeniseNeural"},
    }

    # Giving a provider's voices back removes its older entries too: none can come back.
    await module._write(user_id, EDGE, {}, credential_fingerprint=CREDENTIAL)
    assert await _column(maker, user_id) == {FISH: {"male": "m-new"}}
    assert await _column(maker, neighbour.id) == neighbours


async def test_a_save_over_a_column_that_holds_no_object_stores_one(
    person: tuple[UUID, async_sessionmaker[AsyncSession]],
) -> None:
    """An early shape (a bare string) reads as no choice and gives way to the save — the
    merge would otherwise have turned the column into an array."""
    user_id, maker = person
    async with maker() as setup:
        await setup.execute(update(User).where(User.id == user_id).values(lia_voices="b" * 32))
        await setup.commit()

    await module._write(
        user_id, EDGE, {"female": "fr-FR-DeniseNeural"}, credential_fingerprint=CREDENTIAL
    )

    assert await _column(maker, user_id) == {EDGE: {"female": "fr-FR-DeniseNeural"}}
