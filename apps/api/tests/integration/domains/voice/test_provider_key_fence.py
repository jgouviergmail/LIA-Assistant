"""A catalogue read under account A cannot authorize a write after a key rotation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import Request

from src.core.exceptions import BaseAPIException
from src.core.security.utils import decrypt_data
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.credential_fence import credential_fingerprint, credential_is_current
from src.domains.llm_config.models import ProviderApiKey
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.domains.llm_config.service import LLMConfigService, upsert_provider_key_uncommitted
from src.domains.users.models import AdminAuditLog, User
from src.domains.voice import engine_voices as engines
from src.domains.voice import lia_voices as choices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.fishaudio import catalogue_revision as revisions
from src.domains.voice.fishaudio import library_service as library
from src.domains.voice.fishaudio.design_store import CandidateClaim
from src.domains.voice.fishaudio.library import DesignCandidate, VoiceSample
from src.domains.voice.slot_selection import LibrarySpeechGuard
from src.domains.voice.voices_catalog import VoiceOption
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

VOICE = "c" * 32
CONFIG = TTSConfig(provider="fishaudio", model="s2.1-pro", voice_male=VOICE, voice_female=VOICE)


@dataclass
class _World:
    maker: async_sessionmaker[AsyncSession]
    admin: UUID
    person: UUID

    async def rotate(self) -> None:
        async with self.maker() as db:
            await upsert_provider_key_uncommitted(
                db, provider="fishaudio", key="test-account-B", updated_by=self.admin
            )
            await db.commit()


@pytest.fixture
async def world(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_World]:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    for module in [choices, library, revisions]:
        monkeypatch.setattr(module, "get_db_context", context)
    # Simulate a worker which has not received cross-worker invalidation yet.
    monkeypatch.setattr(
        LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: "test-account-A")
    )
    monkeypatch.setattr(library, "fish_api_key", lambda: "test-account-A")
    monkeypatch.setattr(library.settings, "fishaudio_voice_creation_enabled", True)
    monkeypatch.setattr(library, "_audit_done", AsyncMock())
    async with maker() as db:
        prior = await db.scalar(
            select(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio")
        )
        saved = (
            {
                column.name: getattr(prior, column.name)
                for column in ProviderApiKey.__table__.columns
            }
            if prior
            else None
        )
        admin = UserFactory.create(is_superuser=True)
        person = UserFactory.create()
        db.add_all([admin, person])
        await db.flush()
        committed_user_ids.extend([admin.id, person.id])
        await upsert_provider_key_uncommitted(
            db, provider="fishaudio", key="test-account-A", updated_by=admin.id
        )
        await db.commit()
        state = _World(maker, admin.id, person.id)

    async def engine() -> engines.EngineVoices:
        return await engines.offered_engine(CONFIG)

    monkeypatch.setattr(choices, "chat_engine", engine)
    try:
        yield state
    finally:
        async with maker() as db:
            await db.execute(delete(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio"))
            if saved is not None:
                db.add(ProviderApiKey(**saved))
            await db.commit()


@pytest.mark.parametrize(
    "rotation", ["during_catalogue", "stale_worker", "during_catalogue_with_reload", "removed_key"]
)
async def test_old_account_catalogue_cannot_authorize_a_personal_choice(
    world: _World, monkeypatch: pytest.MonkeyPatch, rotation: str
) -> None:
    if rotation == "stale_worker":
        await world.rotate()
    if rotation == "removed_key":
        async with world.maker() as db:
            await db.execute(delete(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio"))
            await db.commit()

    async def catalogue(api_key: str, *args: object, **kwargs: object) -> list[VoiceOption]:
        assert api_key == "test-account-A"
        if rotation in {"during_catalogue", "during_catalogue_with_reload"}:
            await world.rotate()
        if rotation == "during_catalogue_with_reload":
            monkeypatch.setattr(
                LLMConfigOverrideCache,
                "get_api_key",
                classmethod(lambda cls, provider: "test-account-B"),
            )
        return [VoiceOption(VOICE, "Account A private voice", "male", "fr")]

    monkeypatch.setattr(engines, "get_fish_voices", catalogue)
    with pytest.raises(BaseAPIException) as refusal:
        await choices.save_lia_voices(world.person, "fr", {"male": VOICE})
    assert refusal.value.status_code == 422
    async with world.maker() as db:
        assert await db.scalar(select(User.lia_voices).where(User.id == world.person)) is None


@pytest.mark.parametrize("operation", ["clone", "design", "save", "rename", "delete", "pin"])
async def test_stale_worker_key_cannot_admit_a_library_vendor_mutation(
    world: _World, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    await world.rotate()
    vendor = AsyncMock(side_effect=AssertionError("old-account vendor mutation dispatched"))
    monkeypatch.setattr(library, "design_voices", vendor)
    monkeypatch.setattr(library, "create_voice", vendor)
    monkeypatch.setattr(library, "rename_voice", vendor)
    monkeypatch.setattr(library, "delete_voice", vendor)
    monkeypatch.setattr(library, "add_pin", vendor)
    monkeypatch.setattr(library, "read_pins", AsyncMock(return_value=()))
    monkeypatch.setattr(
        library,
        "fetch_fish_voice",
        AsyncMock(return_value=VoiceOption(VOICE, "Fixture", "male", "fr")),
    )
    monkeypatch.setattr(
        library,
        "claim_candidate",
        AsyncMock(
            return_value=CandidateClaim(
                "d" * 32,
                "test-token",
                DesignCandidate(b"RIFF-fixture", 10, "Hi", "en"),
                credential_fingerprint("test-account-A"),
            )
        ),
    )
    monkeypatch.setattr(library, "release_candidate", AsyncMock())
    monkeypatch.setattr(
        library.UsageLimitService, "instance_budget_block", AsyncMock(return_value=None)
    )
    actor = library.Actor(world.admin, None, None)

    with pytest.raises(BaseAPIException) as refusal:
        if operation == "clone":
            await library.clone_voice(
                actor,
                title="Fixture",
                samples=[VoiceSample("test.wav", b"RIFF-fixture", "audio/wav")],
                texts=(),
                enhance_audio_quality=False,
                consent=True,
            )
        elif operation == "design":
            await library.design(
                actor, instruction="Calm voice", count=1, preview_text=None, language=None
            )
        elif operation == "save":
            await library.save_design(actor, "d" * 32, title="Fixture")
        elif operation == "delete":
            await library.delete(actor, VOICE)
        elif operation == "pin":
            await library.pin(actor, VOICE, attested=True)
        else:
            await library.rename(actor, VOICE, title="Fixture")
    assert refusal.value.status_code == 409
    assert refusal.value.detail["code"] == "fishaudio_account_changed"
    vendor.assert_not_awaited()


async def test_a_current_account_catalogue_can_still_authorize_a_personal_choice(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalogue = AsyncMock(return_value=[VoiceOption(VOICE, "Fixture", "male", "fr")])
    monkeypatch.setattr(engines, "get_fish_voices", catalogue)

    await choices.save_lia_voices(world.person, "fr", {"male": VOICE})

    catalogue.assert_awaited_once()
    async with world.maker() as db:
        assert await db.scalar(select(User.lia_voices).where(User.id == world.person)) == {
            "fishaudio/s2.1-pro": {"male": VOICE}
        }


async def test_a_slot_cannot_select_from_a_catalogue_whose_credential_changed(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def catalogue(api_key: str, *args: object, **kwargs: object) -> list[VoiceOption]:
        assert api_key == "test-account-A"
        await world.rotate()
        return [VoiceOption(VOICE, "Fixture", "male", "fr")]

    monkeypatch.setattr(engines, "get_fish_voices", catalogue)
    async with world.maker() as db:
        with pytest.raises(BaseAPIException) as refusal:
            await LLMConfigService(db, speech_guard=LibrarySpeechGuard()).update_config(
                "voice_tts",
                LLMTypeConfigUpdate(
                    provider="fishaudio",
                    model="s2.1-pro",
                    provider_config=json.dumps({"voice_male": VOICE, "voice_female": VOICE}),
                ),
                world.admin,
                Request({"type": "http", "method": "PUT", "path": "/", "headers": []}),
            )
        assert refusal.value.status_code == 422
        assert refusal.value.detail["type"] == "fishaudio_voice_unavailable"
        await db.rollback()


async def test_a_rotation_waits_until_the_validated_local_write_transaction_finishes(
    world: _World,
) -> None:
    pid = asyncio.get_running_loop().create_future()

    async def rotating() -> None:
        async with world.maker() as db:
            pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            await upsert_provider_key_uncommitted(
                db, provider="fishaudio", key="test-account-B", updated_by=world.admin
            )
            await db.commit()

    async with world.maker() as db:
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-A")
        )
        task = asyncio.create_task(rotating())
        try:
            waiting_pid = await asyncio.wait_for(pid, timeout=2)
            async with asyncio.timeout(3):
                while True:
                    async with world.maker() as observer:
                        blocked = await observer.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": waiting_pid},
                        )
                    if blocked:
                        break
                    assert (
                        not task.done()
                    ), "rotation committed while the validated write still held its transaction"
                    await asyncio.sleep(0.01)
        finally:
            await db.commit()
            await asyncio.wait_for(task, timeout=3)
    async with world.maker() as db:
        assert not await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-A")
        )
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-B")
        )


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
async def test_provider_key_write_rechecks_the_current_administrator(
    world: _World, monkeypatch: pytest.MonkeyPatch, operation: str, revocation: str
) -> None:
    changes = {
        "demoted": {"is_superuser": False},
        "inactive": {"is_active": False},
        "deleted": {"deleted_at": datetime.now(UTC)},
    }
    async with world.maker() as db:
        await db.execute(update(User).where(User.id == world.admin).values(**changes[revocation]))
        await db.commit()
    invalidate = AsyncMock()
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", invalidate)
    request = Request({"type": "http", "method": "PUT", "path": "/", "headers": []})

    async with world.maker() as db:
        try:
            with pytest.raises(BaseAPIException) as refusal:
                service = LLMConfigService(db)
                if operation == "update":
                    await service.update_provider_key(
                        "fishaudio", "test-account-C", world.admin, request
                    )
                else:
                    await service.delete_provider_key("fishaudio", world.admin, request)
            assert refusal.value.status_code == 403
        finally:
            await db.rollback()
    invalidate.assert_not_awaited()
    async with world.maker() as db:
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-A")
        )


async def test_two_initial_key_writes_do_not_fail_after_the_other_insert_commits(
    world: _World,
) -> None:
    async with world.maker() as db:
        await db.execute(delete(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio"))
        await db.commit()
    pid = asyncio.get_running_loop().create_future()

    async def second_write() -> None:
        async with world.maker() as db:
            pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            await upsert_provider_key_uncommitted(
                db, provider="fishaudio", key="test-account-B", updated_by=world.admin
            )
            await db.commit()

    async with world.maker() as first:
        await upsert_provider_key_uncommitted(
            first, provider="fishaudio", key="test-account-A", updated_by=world.admin
        )
        second = asyncio.create_task(second_write())
        try:
            waiting_pid = await asyncio.wait_for(pid, timeout=2)
            async with asyncio.timeout(3):
                while True:
                    async with world.maker() as observer:
                        blocked = await observer.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": waiting_pid},
                        )
                    if blocked:
                        break
                    assert (
                        not second.done()
                    ), "the second key write did not wait for the uncommitted insert"
                    await asyncio.sleep(0.01)
        finally:
            await first.commit()
            await asyncio.wait_for(second, timeout=3)
    async with world.maker() as db:
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-B")
        )


async def test_upsert_refreshes_a_provider_row_already_loaded_by_the_caller(world: _World) -> None:
    async with world.maker() as db:
        loaded = await db.scalar(
            select(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio")
        )
        assert loaded is not None
        await upsert_provider_key_uncommitted(
            db, provider="fishaudio", key="test-account-C", updated_by=world.admin
        )
        assert decrypt_data(loaded.encrypted_key) == "test-account-C"
        assert loaded.updated_by == world.admin
        await db.rollback()


async def test_current_administrator_key_writes_commit_audit_and_invalidate_cache(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalidate = AsyncMock()
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", invalidate)
    request = Request({"type": "http", "method": "PUT", "path": "/", "headers": []})
    async with world.maker() as db:
        service = LLMConfigService(db)
        await service.update_provider_key("fishaudio", "test-account-C", world.admin, request)
        assert invalidate.await_count == 1
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-C")
        )
        await db.commit()
        await service.delete_provider_key("fishaudio", world.admin, request)
        assert invalidate.await_count == 2
    async with world.maker() as db:
        assert (
            await db.scalar(select(ProviderApiKey).where(ProviderApiKey.provider == "fishaudio"))
            is None
        )
        events = (
            await db.scalars(
                select(AdminAuditLog)
                .where(AdminAuditLog.admin_user_id == world.admin)
                .order_by(AdminAuditLog.created_at)
            )
        ).all()
        assert [event.action for event in events] == [
            "provider_api_key_updated",
            "provider_api_key_deleted",
        ]
        assert all(event.details == {"provider": "fishaudio"} for event in events)


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
async def test_key_authority_is_checked_after_waiting_for_the_provider_row(
    world: _World, monkeypatch: pytest.MonkeyPatch, operation: str, revocation: str
) -> None:
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", AsyncMock())
    pid = asyncio.get_running_loop().create_future()
    request = Request({"type": "http", "method": "PUT", "path": "/", "headers": []})

    async def writing() -> BaseAPIException | None:
        async with world.maker() as db:
            pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            try:
                service = LLMConfigService(db)
                if operation == "update":
                    await service.update_provider_key(
                        "fishaudio", "test-account-C", world.admin, request
                    )
                else:
                    await service.delete_provider_key("fishaudio", world.admin, request)
            except BaseAPIException as exc:
                return exc
            finally:
                await db.rollback()
        return None

    async with world.maker() as keeper:
        await keeper.execute(
            select(ProviderApiKey.id)
            .where(ProviderApiKey.provider == "fishaudio")
            .with_for_update()
        )
        task = asyncio.create_task(writing())
        try:
            waiting_pid = await asyncio.wait_for(pid, timeout=2)
            async with asyncio.timeout(3):
                while True:
                    async with world.maker() as observer:
                        blocked = await observer.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": waiting_pid},
                        )
                    if blocked:
                        break
                    assert not task.done(), "key write bypassed the locked provider row"
                    await asyncio.sleep(0.01)
            changes = {
                "demoted": {"is_superuser": False},
                "inactive": {"is_active": False},
                "deleted": {"deleted_at": datetime.now(UTC)},
            }
            async with asyncio.timeout(3):
                async with world.maker() as revoking:
                    await revoking.execute(
                        update(User).where(User.id == world.admin).values(**changes[revocation])
                    )
                    await revoking.commit()
        finally:
            await keeper.commit()
            result = await asyncio.wait_for(task, timeout=3)
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 403
    async with world.maker() as db:
        assert await credential_is_current(
            db, "fishaudio", credential_fingerprint("test-account-A")
        )
