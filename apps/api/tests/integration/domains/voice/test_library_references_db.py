"""Library safety reads committed slot references, never a worker's stale cache."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, event, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import Request

from src.core.exceptions import BaseAPIException
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.llm_config.models import LLMConfigOverride
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.domains.llm_config.service import LLMConfigService
from src.domains.users.models import User
from src.domains.voice import engine_voices as engine_module
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.fishaudio import catalogue_revision as revision_module
from src.domains.voice.fishaudio import library_service as module
from src.domains.voice.fishaudio import pins as pins_module
from src.domains.voice.fishaudio import voices as voices_module
from src.domains.voice.fishaudio.design_store import CandidateClaim, StoredCandidate
from src.domains.voice.fishaudio.library import DesignCandidate, LibraryVoice, VoiceSample
from src.domains.voice.fishaudio.library import delete_voice as vendor_delete
from src.domains.voice.fishaudio.models import FishAudioCatalogueRevision, FishAudioPinnedVoice
from src.domains.voice.fishaudio.voices import FishVoicesError
from src.domains.voice.provider_capacity import ProviderCapacityUnavailable
from src.domains.voice.slot_selection import LibrarySpeechGuard
from src.domains.voice.voices_catalog import VoiceOption
from tests.fixtures.factories import UserFactory
from tests.helpers.provider_keys import provider_key_scope

pytestmark = pytest.mark.integration

VOICE = "b" * 32
SLOT = "voice_tts"


@pytest.fixture
def borrowed(async_engine: AsyncEngine) -> Iterator[set[int]]:
    """Observe checkout/checkin on the fixture's actual pool, including NullPool."""
    active: set[int] = set()

    def checkout(connection: object, record: object, proxy: object) -> None:
        active.add(id(record))

    def checkin(connection: object, record: object) -> None:
        active.discard(id(record))

    event.listen(async_engine.sync_engine, "checkout", checkout)
    event.listen(async_engine.sync_engine, "checkin", checkin)
    try:
        yield active
    finally:
        event.remove(async_engine.sync_engine, "checkout", checkout)
        event.remove(async_engine.sync_engine, "checkin", checkin)


@pytest_asyncio.fixture
async def store(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
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
    monkeypatch.setattr(pins_module, "get_db_context", committed)
    monkeypatch.setattr(module, "fish_api_key", lambda: "test-key")
    monkeypatch.setattr(module, "_audit_done", AsyncMock())
    monkeypatch.setattr(module, "invalidate_fish_voices", AsyncMock())
    monkeypatch.setattr(module, "forget_voice", AsyncMock(return_value=0))
    async with maker() as db:
        await db.execute(delete(FishAudioCatalogueRevision))
        prior = await db.scalar(select(LLMConfigOverride).where(LLMConfigOverride.llm_type == SLOT))
        saved = (
            {
                column.name: getattr(prior, column.name)
                for column in LLMConfigOverride.__table__.columns
            }
            if prior
            else None
        )
        await db.execute(delete(LLMConfigOverride).where(LLMConfigOverride.llm_type == SLOT))
        await db.commit()
    try:
        async with provider_key_scope(maker, provider="fishaudio", key="test-key"):
            yield maker
    finally:
        async with maker() as db:
            await db.execute(delete(FishAudioCatalogueRevision))
            await db.execute(delete(LLMConfigOverride).where(LLMConfigOverride.llm_type == SLOT))
            if saved is not None:
                db.add(LLMConfigOverride(**saved))
            await db.commit()


async def test_configuration_cannot_select_a_voice_while_its_deletion_is_in_flight(
    store: async_sessionmaker[AsyncSession],
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    borrowed: set[int],
) -> None:
    async with store() as db:
        admin = UserFactory.create(is_superuser=True)
        db.add(admin)
        await db.flush()
        committed_user_ids.append(admin.id)
        await db.commit()
        admin_id = admin.id
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", AsyncMock())
    started, finish = asyncio.Event(), asyncio.Event()

    async def deleting(api_key: str, voice_id: str) -> None:
        assert not borrowed
        started.set()
        await asyncio.wait_for(finish.wait(), 5)

    async def offered(config: TTSConfig) -> EngineVoices:
        assert not borrowed
        return EngineVoices(
            config,
            [VoiceOption(VOICE, "Being deleted", "male", "fr")],
            True,
            await revision_module.catalogue_revision(),
            credential_fingerprint=credential_fingerprint("test-key"),
        )

    monkeypatch.setattr(module, "delete_voice", deleting)
    monkeypatch.setattr(engine_module, "offered_engine", offered)
    task = asyncio.create_task(module.delete(module.Actor(admin_id, None, None), VOICE))
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with store() as db:
            with pytest.raises(BaseAPIException) as refusal:
                await LLMConfigService(db, speech_guard=LibrarySpeechGuard()).update_config(
                    SLOT,
                    LLMTypeConfigUpdate(
                        provider="fishaudio",
                        model="s2.1-pro",
                        provider_config=json.dumps({"voice_male": VOICE, "voice_female": VOICE}),
                    ),
                    admin_id,
                    Request({"type": "http", "method": "PUT", "path": "/", "headers": []}),
                )
            assert refusal.value.status_code == 422
            assert refusal.value.detail["type"] == "fishaudio_voice_unavailable"
            await db.rollback()
    finally:
        finish.set()
        await asyncio.wait_for(task, 5)
    async with store() as db:
        assert (
            await db.scalar(select(LLMConfigOverride).where(LLMConfigOverride.llm_type == SLOT))
            is None
        )


async def test_a_configuration_validated_before_unpinning_cannot_restore_the_pin(
    store: async_sessionmaker[AsyncSession],
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with store() as db:
        admin = UserFactory.create(is_superuser=True)
        db.add(admin)
        await db.flush()
        committed_user_ids.append(admin.id)
        await db.commit()
        admin_id = admin.id
    await pins_module.add_pin(
        VOICE, admin_id, credential_fingerprint=credential_fingerprint("test-key")
    )
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", AsyncMock())
    ready, resume = asyncio.Event(), asyncio.Event()

    async def offered(config: TTSConfig) -> EngineVoices:
        revision = await revision_module.catalogue_revision()
        ready.set()
        await asyncio.wait_for(resume.wait(), 5)
        return EngineVoices(
            config,
            [VoiceOption(VOICE, "Previously pinned", "male", "fr")],
            True,
            revision,
            credential_fingerprint=credential_fingerprint("test-key"),
        )

    async def saving() -> None:
        async with store() as db:
            try:
                await LLMConfigService(db, speech_guard=LibrarySpeechGuard()).update_config(
                    SLOT,
                    LLMTypeConfigUpdate(
                        provider="fishaudio",
                        model="s2.1-pro",
                        provider_config=json.dumps({"voice_male": VOICE, "voice_female": VOICE}),
                    ),
                    admin_id,
                    Request({"type": "http", "method": "PUT", "path": "/", "headers": []}),
                )
            except BaseException:
                await db.rollback()
                raise

    monkeypatch.setattr(engine_module, "offered_engine", offered)
    task = asyncio.create_task(saving())
    try:
        await asyncio.wait_for(ready.wait(), 5)
        assert await pins_module.remove_pin(VOICE, admin_id) == ((), True)
        resume.set()
        with pytest.raises(BaseAPIException) as refusal:
            await asyncio.wait_for(task, 5)
        assert refusal.value.status_code == 422
        assert refusal.value.detail["type"] == "fishaudio_voice_unavailable"
    finally:
        resume.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
async def test_a_voice_configuration_rechecks_the_administrator_after_the_catalogue_wait(
    store: async_sessionmaker[AsyncSession],
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    revocation: str,
) -> None:
    async with store() as db:
        admin = UserFactory.create(is_superuser=True)
        db.add(admin)
        await db.flush()
        committed_user_ids.append(admin.id)
        await db.commit()
        admin_id = admin.id
    monkeypatch.setattr(LLMConfigOverrideCache, "invalidate_and_reload", AsyncMock())

    async def offered(config: TTSConfig) -> EngineVoices:
        values = (
            {"is_superuser": False}
            if revocation == "demoted"
            else (
                {"is_active": False}
                if revocation == "inactive"
                else {"deleted_at": datetime.now(UTC)}
            )
        )
        async with store() as other:
            await other.execute(update(User).where(User.id == admin_id).values(**values))
            await other.commit()
        return EngineVoices(
            config,
            [VoiceOption(VOICE, "Available", "male", "fr")],
            True,
            await revision_module.catalogue_revision(),
            credential_fingerprint=credential_fingerprint("test-key"),
        )

    monkeypatch.setattr(engine_module, "offered_engine", offered)
    async with store() as db:
        with pytest.raises(BaseAPIException) as refusal:
            await LLMConfigService(db, speech_guard=LibrarySpeechGuard()).update_config(
                SLOT,
                LLMTypeConfigUpdate(
                    provider="fishaudio",
                    model="s2.1-pro",
                    provider_config=json.dumps({"voice_male": VOICE, "voice_female": VOICE}),
                ),
                admin_id,
                Request({"type": "http", "method": "PUT", "path": "/", "headers": []}),
            )
        assert refusal.value.status_code == 403
        await db.rollback()
    async with store() as db:
        assert (
            await db.scalar(select(LLMConfigOverride).where(LLMConfigOverride.llm_type == SLOT))
            is None
        )


@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
async def test_pin_refuses_authority_revoked_while_vendor_catalogue_was_loading(
    store: async_sessionmaker[AsyncSession],
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    borrowed: set[int],
    revocation: str,
) -> None:
    voice_id = uuid4().hex
    async with store() as db:
        admin = UserFactory.create(is_superuser=True)
        db.add(admin)
        await db.flush()
        committed_user_ids.append(admin.id)
        await db.commit()
        admin_id = admin.id

    async def catalogue(api_key: str, requested: str) -> VoiceOption:
        assert not borrowed
        values = (
            {"is_superuser": False}
            if revocation == "demoted"
            else (
                {"is_active": False}
                if revocation == "inactive"
                else {"deleted_at": datetime.now(UTC)}
            )
        )
        async with store() as other:
            await other.execute(update(User).where(User.id == admin_id).values(**values))
            await other.commit()
        return VoiceOption(requested, "Public voice", "male", "fr")

    monkeypatch.setattr(module, "fetch_fish_voice", catalogue)
    try:
        with pytest.raises(BaseAPIException) as refusal:
            await module.pin(module.Actor(admin_id, None, None), voice_id, attested=True)
        assert refusal.value.status_code == 403
        async with store() as db:
            assert (
                await db.scalar(
                    select(FishAudioPinnedVoice).where(FishAudioPinnedVoice.voice_id == voice_id)
                )
                is None
            )
    finally:
        async with store() as db:
            await db.execute(
                delete(FishAudioPinnedVoice).where(FishAudioPinnedVoice.voice_id == voice_id)
            )
            await db.commit()


@pytest_asyncio.fixture
async def library_admin(
    store: async_sessionmaker[AsyncSession], committed_user_ids: list[UUID]
) -> module.Actor:
    async with store() as db:
        admin = UserFactory.create(is_superuser=True)
        db.add(admin)
        await db.flush()
        committed_user_ids.append(admin.id)
        await db.commit()
        return module.Actor(admin.id, None, None)


async def _revoke_library_admin(
    store: async_sessionmaker[AsyncSession], actor: module.Actor, revocation: str
) -> None:
    changes = {
        "demoted": {"is_superuser": False},
        "inactive": {"is_active": False},
        "deleted": {"deleted_at": datetime.now(UTC)},
    }
    async with store() as other:
        await other.execute(
            update(User).where(User.id == actor.admin_id).values(**changes[revocation])
        )
        await other.commit()


@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
@pytest.mark.parametrize("operation", ["clone", "design", "save_design", "rename"])
async def test_library_vendor_mutation_requires_current_administrator(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    monkeypatch: pytest.MonkeyPatch,
    borrowed: set[int],
    operation: str,
    revocation: str,
) -> None:
    monkeypatch.setattr(module.settings, "fishaudio_voice_creation_enabled", True)
    vendor = AsyncMock(
        side_effect=AssertionError("mutation dispatched after authority was revoked")
    )
    for name in ["create_voice", "design_voices", "rename_voice"]:
        monkeypatch.setattr(module, name, vendor)

    async def budget() -> None:
        assert not borrowed
        await _revoke_library_admin(store, library_admin, revocation)

    async def candidate(candidate_id: str) -> CandidateClaim:
        assert not borrowed
        await _revoke_library_admin(store, library_admin, revocation)
        return CandidateClaim(
            candidate_id,
            "test-token",
            DesignCandidate(b"RIFF-fixture", 10, "Hello", "en"),
            credential_fingerprint("test-key"),
        )

    monkeypatch.setattr(module.UsageLimitService, "instance_budget_block", staticmethod(budget))
    monkeypatch.setattr(module, "claim_candidate", candidate)
    monkeypatch.setattr(module, "release_candidate", AsyncMock())
    if operation in {"clone", "rename"}:
        await _revoke_library_admin(store, library_admin, revocation)
    with pytest.raises(BaseAPIException) as refusal:
        if operation == "clone":
            await module.clone_voice(
                library_admin,
                title="Fixture",
                samples=[VoiceSample("sample.wav", b"RIFF-fixture", "audio/wav")],
                texts=(),
                enhance_audio_quality=False,
                consent=True,
            )
        elif operation == "design":
            await module.design(
                library_admin, instruction="Calm voice", count=1, preview_text=None, language=None
            )
        elif operation == "save_design":
            await module.save_design(library_admin, uuid4().hex, title="Fixture")
        else:
            await module.rename(library_admin, uuid4().hex, title="Fixture")
    assert refusal.value.status_code == 403
    vendor.assert_not_awaited()


@pytest.mark.parametrize("revocation", ["demoted", "inactive", "deleted"])
@pytest.mark.parametrize("operation", ["delete", "unpin"])
async def test_library_removal_rechecks_authority_after_catalogue_wait(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    revocation: str,
) -> None:
    voice_id = uuid4().hex
    entered = asyncio.Event()
    vendor = AsyncMock(side_effect=AssertionError("delete dispatched after authority was revoked"))
    monkeypatch.setattr(module, "delete_voice", vendor)
    if operation == "unpin":
        async with store() as db:
            db.add(FishAudioPinnedVoice(voice_id=voice_id, pinned_by=library_admin.admin_id))
            await db.commit()
    original_lock = revision_module.lock_catalogue

    async def waiting_lock(db: AsyncSession) -> None:
        entered.set()
        await original_lock(db)

    monkeypatch.setattr(module, "lock_catalogue", waiting_lock)
    monkeypatch.setattr(pins_module, "lock_catalogue", waiting_lock)
    task: asyncio.Task[object] | None = None
    try:
        async with store() as holder:
            await original_lock(holder)
            mutation = module.delete if operation == "delete" else module.unpin
            task = asyncio.create_task(mutation(library_admin, voice_id))
            await asyncio.wait_for(entered.wait(), 5)
            await _revoke_library_admin(store, library_admin, revocation)
            await holder.commit()
            with pytest.raises(BaseAPIException) as refusal:
                await asyncio.wait_for(task, 5)
            assert refusal.value.status_code == 403
        vendor.assert_not_awaited()
        async with store() as db:
            assert await revision_module.pending_removals(db) == {}
            if operation == "unpin":
                assert (
                    await db.scalar(
                        select(FishAudioPinnedVoice.id).where(
                            FishAudioPinnedVoice.voice_id == voice_id
                        )
                    )
                    is not None
                )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with store() as db:
            await db.execute(
                delete(FishAudioPinnedVoice).where(FishAudioPinnedVoice.voice_id == voice_id)
            )
            await db.commit()


@pytest.mark.parametrize("operation", ["clone", "design", "save_design", "rename", "delete", "pin"])
async def test_current_admin_dispatches_once_without_holding_sql_during_vendor_io(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    borrowed: set[int],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    voice_id = uuid4().hex
    candidate = DesignCandidate(b"RIFF-fixture", 10, "Hello", "en")
    calls: list[str] = []
    monkeypatch.setattr(module.settings, "fishaudio_voice_creation_enabled", True)

    async def create(*args: object, **kwargs: object) -> LibraryVoice:
        assert not borrowed
        calls.append("create")
        return LibraryVoice(voice_id, "Fixture", "trained", ("en",), "2026-10-15T00:00:00Z")

    async def design(*args: object, **kwargs: object) -> list[DesignCandidate]:
        assert not borrowed
        calls.append("design")
        return [candidate]

    async def mutate(*args: object, **kwargs: object) -> None:
        assert not borrowed
        calls.append("mutate")

    async def fetch(*args: object, **kwargs: object) -> VoiceOption:
        assert not borrowed
        calls.append("fetch")
        return VoiceOption(voice_id, "Fixture", "male", "en")

    monkeypatch.setattr(module, "create_voice", create)
    monkeypatch.setattr(module, "design_voices", design)
    monkeypatch.setattr(module, "rename_voice", mutate)
    monkeypatch.setattr(module, "delete_voice", mutate)
    monkeypatch.setattr(module, "fetch_fish_voice", fetch)
    monkeypatch.setattr(
        module.UsageLimitService, "instance_budget_block", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(module, "record_instance_fixed_spend", AsyncMock())
    monkeypatch.setattr(
        module,
        "claim_candidate",
        AsyncMock(
            return_value=CandidateClaim(
                uuid4().hex, "test", candidate, credential_fingerprint("test-key")
            )
        ),
    )
    monkeypatch.setattr(
        module, "keep_candidates", AsyncMock(return_value=[StoredCandidate(uuid4().hex, candidate)])
    )
    monkeypatch.setattr(module, "forget_candidate", AsyncMock())
    try:
        if operation == "clone":
            await module.clone_voice(
                library_admin,
                title="Fixture",
                samples=[VoiceSample("sample.wav", b"RIFF-fixture", "audio/wav")],
                texts=(),
                enhance_audio_quality=False,
                consent=True,
            )
        elif operation == "design":
            await module.design(
                library_admin, instruction="Calm voice", count=1, preview_text=None, language=None
            )
        elif operation == "save_design":
            await module.save_design(library_admin, uuid4().hex, title="Fixture")
        elif operation == "rename":
            await module.rename(library_admin, voice_id, title="Fixture")
        elif operation == "delete":
            await module.delete(library_admin, voice_id)
        else:
            await module.pin(library_admin, voice_id, attested=True)
        assert len(calls) == 1
        assert not borrowed
    finally:
        async with store() as db:
            await db.execute(
                delete(FishAudioPinnedVoice).where(FishAudioPinnedVoice.voice_id == voice_id)
            )
            await db.commit()


async def test_cancellation_stays_reserved_until_an_explicit_delete_confirms_absence(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = library_admin
    outcomes: list[BaseException] = [
        asyncio.CancelledError(),
        FishVoicesError("key refused", kind="unauthorized"),
        FishVoicesError("already gone", kind="not_found"),
    ]

    async def deleting(api_key: str, voice_id: str) -> None:
        raise outcomes.pop(0)

    monkeypatch.setattr(module, "delete_voice", deleting)
    with pytest.raises(asyncio.CancelledError):
        await module.delete(actor, VOICE)
    async with store() as db:
        assert VOICE in await revision_module.pending_removals(db)
    with pytest.raises(BaseAPIException) as refusal:
        await module.delete(actor, VOICE)
    assert refusal.value.status_code == 502
    async with store() as db:
        assert VOICE in await revision_module.pending_removals(db)
    await module.delete(actor, VOICE)
    async with store() as db:
        assert await revision_module.pending_removals(db) == {}


async def test_a_stale_deletion_cannot_clear_a_newer_deletions_reservation(
    store: async_sessionmaker[AsyncSession],
) -> None:
    async with store() as db:
        await revision_module.lock_catalogue(db)
        old, fresh = await revision_module.reserve_removal(db, VOICE)
        assert fresh
        await db.commit()
    async with store() as db:
        await revision_module.lock_catalogue(db)
        current, fresh = await revision_module.reserve_removal(db, VOICE)
        assert not fresh
        await db.commit()
    await module._clear_delete(VOICE, old)
    async with store() as db:
        assert await revision_module.pending_removals(db) == {VOICE: current}
    await module._clear_delete(VOICE, current)
    async with store() as db:
        assert await revision_module.pending_removals(db) == {}


@pytest.mark.parametrize(
    "timed_out", [False, True], ids=["capacity-unavailable", "capacity-wait-timeout"]
)
async def test_a_deletion_never_dispatched_does_not_leave_a_pending_reservation(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    monkeypatch: pytest.MonkeyPatch,
    timed_out: bool,
) -> None:
    sent: list[str] = []

    @asynccontextmanager
    async def unavailable(*args: object, **kwargs: object) -> AsyncIterator[None]:
        if timed_out:
            await asyncio.Event().wait()
        raise ProviderCapacityUnavailable("test capacity is unavailable")
        yield  # pragma: no cover -- an async context manager that refuses to enter

    async def deleting(api_key: str, voice_id: str) -> None:
        def transport(request: httpx.Request) -> httpx.Response:
            sent.append(request.method)
            return httpx.Response(204)

        await vendor_delete(api_key, voice_id, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(voices_module, "provider_slot", unavailable)
    monkeypatch.setattr(voices_module, "FISHAUDIO_VOICES_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(module, "delete_voice", deleting)
    with pytest.raises(BaseAPIException) as refusal:
        await module.delete(library_admin, VOICE)
    assert refusal.value.status_code == 502
    assert sent == []
    async with store() as db:
        assert await revision_module.pending_removals(db) == {}


@pytest.mark.parametrize("committed_in_use", [True, False], ids=["stale-free", "stale-in-use"])
async def test_delete_uses_the_committed_configuration_before_calling_the_vendor(
    store: async_sessionmaker[AsyncSession],
    library_admin: module.Actor,
    monkeypatch: pytest.MonkeyPatch,
    committed_in_use: bool,
) -> None:
    actual = {
        "provider": "fishaudio" if committed_in_use else "edge",
        "model": "s2.1-pro" if committed_in_use else "edge-tts",
        "provider_config": json.dumps({"voice_male": VOICE, "voice_female": VOICE}),
    }
    cached = {**actual, "provider": "edge" if committed_in_use else "fishaudio"}
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_override",
        classmethod(lambda cls, slot: cached if slot == SLOT else None),
    )
    async with store() as db:
        db.add(LLMConfigOverride(llm_type=SLOT, **actual))
        await db.commit()

    called: list[str] = []

    async def deleting(api_key: str, voice_id: str) -> None:
        called.append(voice_id)

    monkeypatch.setattr(module, "delete_voice", deleting)
    actor = library_admin
    if committed_in_use:
        with pytest.raises(BaseAPIException) as refusal:
            await module.delete(actor, VOICE)
        assert refusal.value.status_code == 409
        assert refusal.value.detail == {"code": "fishaudio_voice_in_use", "slots": [SLOT]}
        assert called == []
    else:
        await module.delete(actor, VOICE)
        assert called == [VOICE]
