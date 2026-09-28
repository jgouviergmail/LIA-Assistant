"""Integration: the radio session store against a real Redis (ADR-324).

The unit tests run the store on a hand-written double; this one runs it on the
real client — its pipeline, its hash and sorted-set signatures, the claim
scripts — so a call the double accepts and Redis refuses cannot stay green.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.live_store import (
    ACTIVE_KEY,
    RadioSessionRecord,
    RadioSessions,
    RadioSessionStore,
)
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment, TranscriptLine
from src.domains.radio.programme import Slot
from src.domains.radio.session import EndReason, SessionState
from src.infrastructure.locks.redis_claim import held_claim

pytestmark = pytest.mark.integration

T0 = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {exc}")
    yield redis
    await redis.aclose()


def _opening_state() -> SessionState:
    """A session whose opening is produced."""
    return SessionState(
        started_at=T0,
        stop_at=T0 + timedelta(minutes=30),
        slots=(
            Slot(
                seq=1,
                format=RadioFormat.OPENING,
                station_id=True,
                air_at=T0 + timedelta(seconds=15),
                duration_s=20.0,
            ),
        ),
        produced=frozenset({1}),
    )


def _opening_segment(root: Path) -> ProducedSegment:
    return ProducedSegment(
        title="Opening",
        audio_path=root / "x.mp3",
        duration_s=20.0,
        transcript=(TranscriptLine(role=RadioRole.HOST, text="Hello.", offset_s=2.0, sources=()),),
        dropped_lines=0,
        unrendered=(),
    )


async def _the_player_s_report_round_trips(store: RadioSessionStore) -> None:
    playhead = Playhead(seq=1, position_s=1.5, reported_at=T0)
    await store.write_playhead(playhead)
    assert await store.playhead() == playhead
    assert not await store.stop_requested()


async def _the_state_and_its_segments_round_trip(
    redis_client: Redis,
    store: RadioSessionStore,
    state: SessionState,
    segment: ProducedSegment,
    *,
    user_id: UUID,
    session_id: UUID,
) -> None:
    await store.publish(state, {1: segment})
    assert await store.read_state() == state
    assert [s.title for s in (await store.read_segments([1, 7])).values()] == ["Opening"]
    assert set(await store.read_ready()) == {1}
    assert str(session_id) in await redis_client.zrange(ACTIVE_KEY, 0, -1)
    assert 0 < await redis_client.ttl(f"radio:segments:{user_id}:{session_id}") <= 60


async def _one_loop_holds_the_lease(redis_client: Redis, store: RadioSessionStore) -> None:
    assert await store.claim_loop("worker-a", lease_s=30)
    async with held_claim(redis_client, store.loop_key, "worker-a", ttl_seconds=30):
        assert await store.loop_alive()
        assert not await store.claim_loop("worker-b", lease_s=30)
    assert not await store.loop_alive()


async def test_a_session_round_trips_through_real_redis(
    redis_client: Redis, tmp_path: Path
) -> None:
    user_id, first, second = uuid4(), uuid4(), uuid4()
    sessions = RadioSessions(redis_client, ttl_s=60)
    store = RadioSessionStore(
        redis_client, user_id=user_id, session_id=first, ttl_s=60, media_root=tmp_path
    )
    keys = [
        f"radio:session:{user_id}",
        f"radio:inbox:{user_id}:{first}",
        f"radio:state:{user_id}:{first}",
        f"radio:segments:{user_id}:{first}",
        store.loop_key,
    ]
    state = _opening_state()
    try:
        await sessions.open(
            RadioSessionRecord(session_id=first, user_id=user_id, run_id="radio_x", started_at=T0)
        )
        await _the_player_s_report_round_trips(store)
        await _the_state_and_its_segments_round_trip(
            redis_client,
            store,
            state,
            _opening_segment(tmp_path),
            user_id=user_id,
            session_id=first,
        )
        await _one_loop_holds_the_lease(redis_client, store)

        await sessions.open(
            RadioSessionRecord(session_id=second, user_id=user_id, run_id="radio_y", started_at=T0)
        )
        assert await store.stop_requested()  # the account's place was taken

        await store.publish(replace(state, ended=EndReason.LISTENER), {})
        assert str(first) not in await redis_client.zrange(ACTIVE_KEY, 0, -1)
    finally:
        await redis_client.delete(*keys)
        await redis_client.zrem(ACTIVE_KEY, str(first))
