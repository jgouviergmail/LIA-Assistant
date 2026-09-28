"""The session's shared state: what the routes write, the loop reads, and back."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.live_store import (
    ACTIVE_KEY,
    RadioSessionRecord,
    RadioSessions,
    RadioSessionStore,
    record_key,
)
from src.domains.radio.media import segment_path
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment, TranscriptLine
from src.domains.radio.programme import Slot
from src.domains.radio.session import EndReason, SessionState
from src.infrastructure.cache.key_families import KeyScope, scope_of
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)
USER = UUID("00000000-0000-4000-8000-00000000000a")
TTL = 3600


def record(session_id: UUID) -> RadioSessionRecord:
    return RadioSessionRecord(
        session_id=session_id,
        user_id=USER,
        run_id=f"radio_{session_id.hex}",
        started_at=T0,
        setup={"language": "fr", "voices": {"host": "fr-FR-A"}},
    )


def store(redis: FakeRedis, session_id: UUID, root: Path) -> RadioSessionStore:
    return RadioSessionStore(
        redis,
        user_id=USER,
        session_id=session_id,
        ttl_s=TTL,
        media_root=root,
        clock=lambda: T0 + timedelta(minutes=1),
    )


def segment(title: str, root: Path) -> ProducedSegment:
    return ProducedSegment(
        title=title,
        audio_path=root / "ignored.mp3",
        duration_s=20.0,
        transcript=(
            TranscriptLine(role=RadioRole.HOST, text="Bonjour.", offset_s=3.0, sources=()),
        ),
        dropped_lines=0,
        unrendered=(),
    )


BASE = SessionState(
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


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


async def test_the_record_comes_back_whole(redis: FakeRedis) -> None:
    session_id = uuid4()
    sessions = RadioSessions(redis, ttl_s=TTL)
    await sessions.open(record(session_id))
    assert await sessions.current(USER) == record(session_id)
    assert redis.ttls[record_key(USER)] == TTL


async def test_the_player_s_last_report_is_what_the_loop_reads(
    redis: FakeRedis, tmp_path: Path
) -> None:
    session = store(redis, uuid4(), tmp_path)
    assert await session.playhead() is None
    first = Playhead(seq=1, position_s=2.0, reported_at=T0)
    last = Playhead(seq=1, position_s=7.0, reported_at=T0 + timedelta(seconds=5), playing=False)
    await session.write_playhead(first)
    await session.write_playhead(last)
    assert await session.playhead() == last


async def test_a_stop_reaches_the_loop(redis: FakeRedis, tmp_path: Path) -> None:
    session_id = uuid4()
    await RadioSessions(redis, ttl_s=TTL).open(record(session_id))
    session = store(redis, session_id, tmp_path)
    assert not await session.stop_requested()
    await session.request_stop()
    assert await session.stop_requested()


async def test_a_new_session_stops_the_account_s_previous_one(
    redis: FakeRedis, tmp_path: Path
) -> None:
    """Two tabs never make two antennas: the second start takes the place."""
    first, second = uuid4(), uuid4()
    sessions = RadioSessions(redis, ttl_s=TTL)
    await sessions.open(record(first))
    await sessions.open(record(second))
    assert await store(redis, first, tmp_path).stop_requested()
    assert not await store(redis, second, tmp_path).stop_requested()


async def test_a_session_whose_record_is_gone_stops(redis: FakeRedis, tmp_path: Path) -> None:
    assert await store(redis, uuid4(), tmp_path).stop_requested()


async def test_segments_are_published_once_and_the_same_state_is_not_rewritten(
    redis: FakeRedis, tmp_path: Path
) -> None:
    session = store(redis, uuid4(), tmp_path)
    ready = {1: segment("Opening", tmp_path)}
    await session.publish(BASE, ready)
    writes = redis.ops["hset"], redis.ops["set"]
    await session.publish(BASE, ready)
    assert (redis.ops["hset"], redis.ops["set"]) == writes

    reported = replace(BASE, playhead=Playhead(seq=1, position_s=4.0, reported_at=T0))
    await session.publish(reported, ready)
    assert redis.ops["hset"] == writes[0]  # the transcript is not written again
    assert redis.ops["set"] == writes[1] + 1
    assert await session.read_state() == reported


async def test_a_segment_s_audio_is_where_the_media_root_puts_it(
    redis: FakeRedis, tmp_path: Path
) -> None:
    session_id = uuid4()
    session = store(redis, session_id, tmp_path)
    await session.publish(BASE, {1: segment("Opening", Path("/somewhere/else"))})
    key = next(name for name in redis.hashes if name.startswith("radio:segments:"))
    stored = json.loads(redis.hashes[key]["1"])
    stored["audio_path"] = "/etc/passwd"  # nothing read back from the store names a file
    redis.hashes[key]["1"] = json.dumps(stored)

    read = await store(redis, session_id, tmp_path).read_segments([1, 2])
    assert set(read) == {1}
    assert read[1].audio_path == segment_path(tmp_path, session_id, 1)
    assert read[1].title == "Opening"
    assert await store(redis, session_id, tmp_path).read_ready() == read


async def test_a_live_session_is_active_and_an_ended_one_leaves(
    redis: FakeRedis, tmp_path: Path
) -> None:
    session_id = uuid4()
    session = store(redis, session_id, tmp_path)
    sessions = RadioSessions(redis, ttl_s=TTL)
    await session.publish(BASE, {})
    assert redis.zsets[ACTIVE_KEY][str(session_id)] == (T0 + timedelta(minutes=1)).timestamp()
    assert await sessions.active_ids(now=T0 + timedelta(minutes=2), horizon_s=600) == {session_id}
    assert await sessions.active_ids(now=T0 + timedelta(minutes=12), horizon_s=600) == set()

    await session.publish(BASE, {})  # unchanged: nothing written
    await session.publish(replace(BASE, ended=EndReason.TIMER), {})
    assert str(session_id) not in redis.zsets[ACTIVE_KEY]


async def test_what_cannot_be_read_back_is_absent_never_a_crash(
    redis: FakeRedis, tmp_path: Path
) -> None:
    session_id = uuid4()
    session = store(redis, session_id, tmp_path)
    await session.publish(BASE, {1: segment("Opening", tmp_path)})
    redis.strings[next(k for k in redis.strings if k.startswith("radio:state:"))] = "{}"
    redis.strings[record_key(USER)] = '{"session_id": "not-a-uuid"}'
    segments_key = next(name for name in redis.hashes if name.startswith("radio:segments:"))
    redis.hashes[segments_key]["1"] = "[]"

    assert await session.read_state() is None
    assert await RadioSessions(redis, ttl_s=TTL).current(USER) is None
    assert await session.read_segments([1]) == {}
    assert await session.stop_requested()  # an unreadable record names no session


class RacingRedis(FakeRedis):
    """Hands over after every join and every count, so two starts interleave step by step."""

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        added = await super().zadd(key, mapping)
        await asyncio.sleep(0)
        return added

    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        members = await super().zrange(key, start, stop)
        await asyncio.sleep(0)
        return members


async def test_two_starts_racing_for_the_last_place_never_both_land() -> None:
    redis = RacingRedis()
    sessions = RadioSessions(redis, ttl_s=60)

    async def admitted(session: UUID) -> bool:
        return await sessions.admit(session, replacing=None, now=T0, horizon_s=120.0, cap=1)

    outcomes = await asyncio.gather(admitted(uuid4()), admitted(uuid4()))

    assert outcomes.count(True) <= 1  # the ceiling holds; both may have to try again
    assert len(await redis.zrange(ACTIVE_KEY, 0, -1)) == outcomes.count(True)


async def test_one_loop_holds_the_lease(redis: FakeRedis, tmp_path: Path) -> None:
    session = store(redis, uuid4(), tmp_path)
    assert not await session.loop_alive()
    assert await session.claim_loop("worker-a", lease_s=30)
    assert not await session.claim_loop("worker-b", lease_s=30)
    assert await session.loop_alive()


async def test_every_key_is_a_declared_family(redis: FakeRedis, tmp_path: Path) -> None:
    """A reset never stops the antenna; account deletion reaches every key."""
    session_id = uuid4()
    await RadioSessions(redis, ttl_s=TTL).open(record(session_id))
    session = store(redis, session_id, tmp_path)
    await session.write_playhead(Playhead(seq=1, position_s=0.0, reported_at=T0))
    await session.publish(BASE, {1: segment("Opening", tmp_path)})
    await session.claim_loop("worker-a", lease_s=30)
    user_keys = [*redis.strings, *redis.hashes]
    assert len(user_keys) == 5
    assert all(str(USER) in key for key in user_keys)
    assert {scope_of(key) for key in user_keys} == {KeyScope.USER_RUNTIME}
    assert scope_of(ACTIVE_KEY) is KeyScope.GLOBAL
