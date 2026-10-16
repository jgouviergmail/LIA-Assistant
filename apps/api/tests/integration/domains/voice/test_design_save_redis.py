"""A designed preview may create at most one voice while its outcome is uncertain."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.llm_config.credential_fence import credential_fingerprint
from src.domains.voice.fishaudio import design_store, library_service
from src.domains.voice.fishaudio.library import DesignCandidate, LibraryVoice
from src.domains.voice.fishaudio.voices import FishVoicesError

pytestmark = pytest.mark.integration


class _WriteFault:
    """Keep reads live while a post-vendor acknowledgement cannot be persisted."""

    def __init__(self, client: Redis) -> None:
        self.client = client
        self.fail_writes = False
        self.lose_next_ack = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    async def _write(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.fail_writes:
            raise RedisConnectionError("test write unavailable")
        result = await getattr(self.client, name)(*args, **kwargs)
        if self.lose_next_ack:
            self.lose_next_ack = False
            raise RedisConnectionError("test acknowledgement lost after write")
        return result

    async def eval(self, *args: Any, **kwargs: Any) -> Any:
        return await self._write("eval", *args, **kwargs)

    async def set(self, *args: Any, **kwargs: Any) -> Any:
        return await self._write("set", *args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        return await self._write("delete", *args, **kwargs)


@dataclass
class _World:
    redis: Redis
    fault: _WriteFault
    candidate_id: str
    vendor: AsyncMock


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_World]:
    client = Redis.from_url(str(settings.redis_url), decode_responses=True)
    await client.ping()
    prefix = f"test:design-save:{uuid4().hex}:"
    fault = _WriteFault(client)

    async def cache() -> Any:
        return fault

    monkeypatch.setattr(design_store, "REDIS_KEY_FISHAUDIO_DESIGN_PREFIX", prefix)
    monkeypatch.setattr(design_store, "get_redis_cache", cache)
    monkeypatch.setattr(library_service, "fish_api_key", lambda: "test-fish-key")
    monkeypatch.setattr(library_service.settings, "fishaudio_voice_creation_enabled", True)
    monkeypatch.setattr(library_service, "_authorize", AsyncMock())
    monkeypatch.setattr(library_service, "_audit_done", AsyncMock())
    monkeypatch.setattr(library_service, "invalidate_fish_voices", AsyncMock())
    vendor = AsyncMock(return_value=LibraryVoice(uuid4().hex, "Fixture", "trained", (), None))
    monkeypatch.setattr(library_service, "create_voice", vendor)
    (kept,) = await design_store.keep_candidates(
        [DesignCandidate(b"RIFF-test", 10, "Hi", "en")],
        credential_fingerprint=credential_fingerprint("test-fish-key"),
    )
    try:
        yield _World(client, fault, kept.candidate_id, vendor)
    finally:
        keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


async def _save(world: _World) -> LibraryVoice | BaseAPIException:
    try:
        return await library_service.save_design(
            library_service.Actor(uuid4(), None, None), world.candidate_id, title="Fixture"
        )
    except BaseAPIException as exc:
        return exc


def _assert_pending(result: LibraryVoice | BaseAPIException) -> None:
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 409
    assert result.detail["code"] == "fishaudio_design_save_pending"


async def test_two_administrators_cannot_save_the_same_preview_twice(world: _World) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def create(*args: Any, **kwargs: Any) -> LibraryVoice:
        if world.vendor.await_count == 1:
            started.set()
            await release.wait()
        return LibraryVoice(uuid4().hex, "Fixture", "trained", (), None)

    world.vendor.side_effect = create
    first = asyncio.create_task(_save(world))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        second = await asyncio.wait_for(_save(world), timeout=2)
    finally:
        release.set()
        await first

    _assert_pending(second)
    assert world.vendor.await_count == 1


async def test_failed_redis_cleanup_cannot_reopen_a_successful_save(world: _World) -> None:
    async def create(*args: Any, **kwargs: Any) -> LibraryVoice:
        world.fault.fail_writes = True
        return LibraryVoice(uuid4().hex, "Fixture", "trained", (), None)

    world.vendor.side_effect = create
    assert isinstance(await _save(world), LibraryVoice)
    world.fault.fail_writes = False

    _assert_pending(await _save(world))
    assert world.vendor.await_count == 1


async def test_an_unknown_vendor_outcome_does_not_authorize_another_creation(world: _World) -> None:
    world.vendor.side_effect = FishVoicesError("test acknowledgement lost")
    result = await _save(world)
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 502

    _assert_pending(await _save(world))
    assert world.vendor.await_count == 1


async def test_cancelling_after_dispatch_does_not_reopen_the_preview(world: _World) -> None:
    started = asyncio.Event()

    async def create(*args: Any, **kwargs: Any) -> LibraryVoice:
        if world.vendor.await_count == 1:
            started.set()
            await asyncio.Event().wait()
        return LibraryVoice(uuid4().hex, "Fixture", "trained", (), None)

    world.vendor.side_effect = create
    first = asyncio.create_task(_save(world))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    _assert_pending(await _save(world))
    assert world.vendor.await_count == 1


@pytest.mark.parametrize("kind", ["payment_required", "unavailable"])
async def test_definitive_refusal_keeps_the_original_audio_for_an_explicit_retry(
    world: _World, kind: str
) -> None:
    expected = await design_store.stored_candidate(world.candidate_id)
    world.vendor.side_effect = FishVoicesError(
        "test refused before effect", kind=kind, effect_may_have_occurred=False
    )
    assert isinstance(await _save(world), BaseAPIException)
    assert await design_store.stored_candidate(world.candidate_id) == expected

    world.vendor.side_effect = None
    assert isinstance(await _save(world), LibraryVoice)
    assert world.vendor.await_count == 2
    assert world.vendor.call_args.kwargs["samples"][0].content == b"RIFF-test"


async def test_success_forgets_the_preview_so_it_cannot_be_saved_again(world: _World) -> None:
    assert isinstance(await _save(world), LibraryVoice)

    result = await _save(world)
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 410
    assert await design_store.stored_candidate(world.candidate_id) is None
    assert world.vendor.await_count == 1


async def test_cancellation_before_admission_restores_the_preview(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()

    async def authorize(actor: library_service.Actor, api_key: str) -> None:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(library_service, "_authorize", authorize)
    first = asyncio.create_task(_save(world))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    assert await design_store.stored_candidate(world.candidate_id) is not None
    world.vendor.assert_not_awaited()

    monkeypatch.setattr(library_service, "_authorize", AsyncMock())
    assert isinstance(await _save(world), LibraryVoice)
    world.vendor.assert_awaited_once()


async def test_claiming_never_refreshes_or_removes_the_original_expiry(world: _World) -> None:
    key = design_store._key(world.candidate_id)
    await world.redis.pexpire(key, 4000)
    claim = await design_store.claim_candidate(world.candidate_id)
    assert claim is not None
    assert 0 < await world.redis.pttl(key) <= 4000
    assert await design_store.stored_candidate(world.candidate_id) is None

    await design_store.release_candidate(claim)
    assert 0 < await world.redis.pttl(key) <= 4000
    assert await design_store.stored_candidate(world.candidate_id) is not None


async def test_an_old_claim_cannot_release_or_forget_a_new_owners_audio(world: _World) -> None:
    first = await design_store.claim_candidate(world.candidate_id)
    assert first is not None
    await design_store.release_candidate(first)
    second = await design_store.claim_candidate(world.candidate_id)
    assert second is not None and second.token != first.token

    await design_store.release_candidate(first)
    await design_store.forget_candidate(first)
    _assert_pending(await _save(world))
    world.vendor.assert_not_awaited()

    await design_store.forget_candidate(second)
    assert await world.redis.exists(design_store._key(world.candidate_id)) == 0


async def test_lost_redis_claim_ack_is_safe_to_retry_before_any_vendor_dispatch(
    world: _World,
) -> None:
    world.fault.lose_next_ack = True
    result = await _save(world)
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 503
    world.vendor.assert_not_awaited()

    assert isinstance(await _save(world), LibraryVoice)
    world.vendor.assert_awaited_once()


async def test_eviction_removes_both_audio_and_ownership_without_allowing_recreation(
    world: _World,
) -> None:
    claim = await design_store.claim_candidate(world.candidate_id)
    assert claim is not None
    await world.redis.delete(design_store._key(world.candidate_id))

    result = await _save(world)
    assert isinstance(result, BaseAPIException)
    assert result.status_code == 410
    world.vendor.assert_not_awaited()


async def test_a_preview_cannot_upload_its_audio_to_a_different_provider_account(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(library_service, "fish_api_key", lambda: "test-other-account")

    result = await _save(world)

    assert isinstance(result, BaseAPIException)
    assert result.status_code == 409
    assert result.detail["code"] == "fishaudio_account_changed"
    world.vendor.assert_not_awaited()
    # There was no dispatch; reconfiguring the original account may still save it.
    assert await design_store.stored_candidate(world.candidate_id) is not None
