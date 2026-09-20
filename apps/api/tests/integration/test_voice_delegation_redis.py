"""Integration: two delegations of one voice session against real Redis (ADR-301).

The unit tests fake the lease and the marker. Here both are the real thing:
the conversation's active-run lock (``active_run_lease``) and the
newest-request marker the bridge polls. Two requests race on one session
from two independent tasks — the shape of two vendor webhooks landing on two
workers — and the first must step aside for the second, releasing the lock
the second then takes.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from redis.asyncio import Redis

import src.infrastructure.scheduler.voice_delegation as bridge
from src.core.config import settings
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.scheduler.out_of_turn_run import RunContext, RunOutcome, RunResult
from src.infrastructure.scheduler.voice_delegation import (
    DelegationOutcome,
    DelegationRequest,
    delegate,
)
from src.infrastructure.streaming.run_stream_broker import active_run_key, get_active_run

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {exc}")
    yield redis
    await redis.aclose()


def _context() -> RunContext:
    return RunContext(
        user=object(),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        display_mode="cards",
    )


async def test_two_requests_on_one_session_the_newest_wins_and_takes_the_lock(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = VoiceSession.phone(
        call_id=uuid.uuid4(),
        mode="delegated",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )
    started: list[str] = []
    cancelled: list[str] = []
    seen_locks: dict[str, dict[str, str] | None] = {}

    async def _redis() -> Redis:
        return redis_client

    async def _pending(_conversation_id: str) -> dict[str, Any] | None:
        return None

    async def _stream(request: Any) -> RunResult:
        started.append(request.prompt)
        # The lock is held while the turn runs — by THIS request's own token.
        seen_locks[request.prompt] = await get_active_run(
            redis_client, str(session.conversation_id)
        )
        try:
            await asyncio.sleep(0.6 if request.prompt == "first" else 0.05)
        except asyncio.CancelledError:
            cancelled.append(request.prompt)
            raise
        return RunResult(outcome=RunOutcome.SUCCESS, text=f"done {request.prompt}", attempts=1)

    monkeypatch.setattr(bridge, "get_redis_cache", _redis)
    monkeypatch.setattr(bridge, "check_pending_hitl_uncached", _pending)
    monkeypatch.setattr(bridge, "stream_instruction", _stream)
    monkeypatch.setattr(bridge, "SUPERSEDE_POLL_SECONDS", 0.02)
    monkeypatch.setattr(settings, "voice_delegation_lease_wait_seconds", 3, raising=False)

    try:
        first = asyncio.create_task(
            delegate(
                DelegationRequest(
                    session=session,
                    request_id="call-1",
                    request="first",
                    spoken_text=None,
                    wait_seconds=5,
                ),
                context=_context(),
            )
        )
        await asyncio.sleep(0.15)
        assert await get_active_run(redis_client, str(session.conversation_id)) == {
            "run_id": f"{session.run_id}:call-1",
            "stream_id": "phone_call:call-1",
        }
        second = asyncio.create_task(
            delegate(
                DelegationRequest(
                    session=session,
                    request_id="call-2",
                    request="second",
                    spoken_text=None,
                    wait_seconds=5,
                ),
                context=_context(),
            )
        )
        first_result, second_result = await asyncio.gather(first, second)
    finally:
        await redis_client.delete(active_run_key(str(session.conversation_id)))
        await redis_client.delete(bridge.newest_request_key(session.key))

    assert first_result.outcome is DelegationOutcome.SUPERSEDED
    assert second_result.outcome is DelegationOutcome.ANSWERED
    assert second_result.text == "done second"
    assert cancelled == ["first"]
    assert started == ["first", "second"]
    # The second ran under its OWN token, once the first's lock was released.
    assert seen_locks["second"] == {
        "run_id": f"{session.run_id}:call-2",
        "stream_id": "phone_call:call-2",
    }
    # Nothing is left behind but the marker, which expires with the turn's bound.
    assert await get_active_run(redis_client, str(session.conversation_id)) is None
