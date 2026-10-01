"""One live session per account, claimed with an owner token; the instance cap (ADR-299)."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.core.constants import (
    LIVE_SESSION_MAX_MINUTES_DEFAULT,
    LIVE_SESSION_RECORD_GRACE_SECONDS,
)
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from tests.unit.domains.live.fakes import FakeRedis

pytestmark = pytest.mark.unit


def _record(user_id: uuid.UUID, token: str = "tok") -> LiveSessionRecord:
    return LiveSessionRecord(
        session_id=uuid.uuid4().hex,
        user_id=user_id,
        provider="gemini",
        model="m",
        run_id="live_session_x",
        started_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        token=token,
    )


def test_the_nonce_survives_the_round_trip_and_reads_none_when_absent() -> None:
    # An offer connection's credential lives on the record; a token connection's
    # record (and one written by the previous release) carries none.
    until = datetime.now(UTC) + timedelta(seconds=30)
    record = replace(_record(uuid.uuid4()), nonce="n" * 40, nonce_until=until)
    back = LiveSessionRecord.from_json(record.to_json())
    assert back.unlimited_cap is False
    rolling = replace(record, unlimited_cap=True)
    assert LiveSessionRecord.from_json(rolling.to_json()).unlimited_cap is True
    assert back.nonce == "n" * 40 and back.nonce_until == until
    bare = json.loads(_record(uuid.uuid4()).to_json())
    del bare["nonce"], bare["nonce_until"]
    older = LiveSessionRecord.from_json(json.dumps(bare))
    assert older.nonce is None and older.nonce_until is None


def test_the_record_round_trip_is_equality_over_every_field() -> None:
    # A field added on one side only is silently lost on the next read — the
    # mode was (ADR-300 wave 4, measured on dev 2026-09-19: a DIRECT session's
    # own tool door refused every lookup as « not a direct session »).
    until = datetime.now(UTC) + timedelta(seconds=30)
    record = replace(
        _record(uuid.uuid4()),
        setup_inputs={"model": "m", "direct_tools": [{"name": "t"}]},
        extensions=2,
        unlimited_cap=True,
        mode="direct",
        nonce="n" * 40,
        nonce_until=until,
    )
    assert LiveSessionRecord.from_json(record.to_json()) == record
    # A record written by the previous release carries no mode: delegated.
    bare = json.loads(_record(uuid.uuid4()).to_json())
    del bare["mode"]
    assert LiveSessionRecord.from_json(json.dumps(bare)).mode == "delegated"


async def test_rewrite_keeps_the_record_under_its_claim_with_its_remaining_life(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user_id = uuid.uuid4()
    record = _record(user_id)
    assert await store.claim(record, ttl_seconds=720)
    now = datetime.now(UTC)
    nonced = replace(record, nonce="n" * 40, nonce_until=now + timedelta(seconds=60))
    assert await store.rewrite(nonced, now=now)
    kept = await store.get(user_id)
    assert kept is not None and kept.nonce == "n" * 40
    # The life is what the record still has: to its cap plus the grace, never the full cap again.
    assert redis.ttls[store._claim_key(user_id)] == nonced.remaining_life_seconds(now)
    assert nonced.remaining_life_seconds(now) < 720
    # A successor's record is not rewritten by the old owner.
    stranger = replace(nonced, token="other")
    assert not await store.rewrite(stranger, now=now)
    assert (await store.get(user_id)) == kept


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def store(redis: FakeRedis) -> LiveSessionStore:
    return LiveSessionStore(redis)


async def test_extend_moves_the_expiry_for_the_owner_only(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # An extension rewrites the record under the SAME claim, owner-checked:
    # a tab that lost its slot to a newer session must not resurrect it.
    user = uuid.uuid4()
    record = _record(user, "a")
    assert await store.claim(record, ttl_seconds=60) is True
    later = record.expires_at + timedelta(minutes=10)
    extended = replace(record, expires_at=later, extensions=1)
    assert await store.extend(extended, ttl_seconds=720) is True
    read = await store.get(user)
    assert read is not None and read.expires_at == later and read.extensions == 1
    assert redis.ttls[f"live:session:{user}"] == 720
    assert redis.ttls[f"live:session:{user}:record"] == 720
    stranger = replace(extended, token="b", extensions=2)
    assert await store.extend(stranger, ttl_seconds=900) is False
    read = await store.get(user)
    assert read is not None and read.extensions == 1 and read.token == "a"


def test_a_record_written_before_the_expiry_field_reads_the_default_cap() -> None:
    # Records live at most a cap plus its grace: the ones written by the
    # previous release are read with the cap they were minted under.
    record = _record(uuid.uuid4())
    payload = json.loads(record.to_json())
    del payload["expires_at"]
    del payload["extensions"]
    read = LiveSessionRecord.from_json(json.dumps(payload))
    assert read.expires_at == record.started_at + timedelta(
        minutes=LIVE_SESSION_MAX_MINUTES_DEFAULT
    )
    assert read.extensions == 0


async def test_second_claim_on_the_same_account_is_refused(store: LiveSessionStore) -> None:
    user = uuid.uuid4()
    assert await store.claim(_record(user, "a"), ttl_seconds=60) is True
    assert await store.claim(_record(user, "b"), ttl_seconds=60) is False


async def test_the_record_round_trips(store: LiveSessionStore) -> None:
    user = uuid.uuid4()
    record = _record(user, "owner")
    await store.claim(record, ttl_seconds=60)
    read = await store.get(user)
    assert read == record


async def test_release_needs_the_owner_token(store: LiveSessionStore, redis: FakeRedis) -> None:
    user = uuid.uuid4()
    await store.claim(_record(user, "owner"), ttl_seconds=60)
    assert await store.release(user, "stranger") is False
    assert await store.get(user) is not None
    assert await store.release(user, "owner") is True
    assert await store.get(user) is None
    # Nothing of the session survives a release: claim AND record are gone.
    assert not [k for k in redis.store if k.startswith("live:session:")]


async def test_a_record_without_its_claim_is_no_session(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user = uuid.uuid4()
    record = _record(user, "owner")
    await store.claim(record, ttl_seconds=60)
    # The claim expired (TTL) while the record lingered a moment longer.
    del redis.store[f"live:session:{user}"]
    assert await store.get(user) is None


async def test_the_claim_and_the_record_carry_the_session_ttl(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user = uuid.uuid4()
    await store.claim(_record(user), ttl_seconds=1800)
    assert redis.ttls[f"live:session:{user}"] == 1800
    assert redis.ttls[f"live:session:{user}:record"] == 1800


async def test_active_set_counts_only_unexpired_sessions(store: LiveSessionStore) -> None:
    now = datetime.now(UTC)
    await store.register_active("s1", now + timedelta(minutes=5))
    await store.register_active("s2", now - timedelta(minutes=1))
    assert await store.count_active(now) == 1
    await store.unregister_active("s1")
    assert await store.count_active(now) == 0


async def test_a_broken_cache_refuses_the_claim(redis: FakeRedis) -> None:
    redis.broken = True
    store = LiveSessionStore(redis)
    with pytest.raises(ConnectionError):
        await store.claim(_record(uuid.uuid4()), ttl_seconds=60)


async def test_the_lookup_budget_counts_per_session_and_lives_as_long_as_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # ADR-300 wave 4: a model in a loop must not spend for ever. The counter is
    # the session's own, expires with its record (set once, on the first
    # lookup), and the limit is inclusive.
    assert await store.consume_tool_budget("s1", limit=2, ttl_seconds=90)
    assert redis.ttls["live_tools:s1"] == 90
    assert await store.consume_tool_budget("s1", limit=2, ttl_seconds=5)
    assert redis.ttls["live_tools:s1"] == 90  # the TTL is set once, never pushed back
    assert not await store.consume_tool_budget("s1", limit=2, ttl_seconds=90)
    # Another session has its own counter.
    assert await store.consume_tool_budget("s2", limit=2, ttl_seconds=90)
    # A record about to expire still gets a positive TTL.
    assert await store.consume_tool_budget("s3", limit=2, ttl_seconds=0)
    assert redis.ttls["live_tools:s3"] == 1


# -- the turns a DIRECT session keeps (ADR-301) ----------------------------------


async def test_the_kept_turns_are_ordered_bounded_and_live_with_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user = uuid.uuid4()
    assert await store.claim(_record(user), ttl_seconds=600) is True
    assert (
        await store.append_turns(
            user, [("user", "a"), ("assistant", "b")], ttl_seconds=600, max_rows=3
        )
        == 2
    )
    # Past the bound the rest is dropped, and the count says how many were kept.
    assert (
        await store.append_turns(
            user, [("user", "c"), ("assistant", "d")], ttl_seconds=590, max_rows=3
        )
        == 1
    )
    assert await store.turns(user) == [("user", "a"), ("assistant", "b"), ("user", "c")]
    assert redis.ttls[f"live:session:{user}:turns"] == 590


async def test_an_extension_keeps_the_turns_alive_as_long_as_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # The list was given the record's remaining life at the last append; an
    # extension that moved the record's cap must move the list's too, or a
    # session extended past its first cap ends with its words already gone.
    user = uuid.uuid4()
    record = _record(user, "a")
    assert await store.claim(record, ttl_seconds=60) is True
    await store.append_turns(user, [("user", "a")], ttl_seconds=30, max_rows=10)
    extended = replace(record, expires_at=record.expires_at + timedelta(minutes=10), extensions=1)
    assert await store.extend(extended, ttl_seconds=720) is True
    assert redis.ttls[f"live:session:{user}:turns"] == 720
    # A successor's extension moves nothing, the list included.
    assert await store.extend(replace(extended, token="b"), ttl_seconds=900) is False
    assert redis.ttls[f"live:session:{user}:turns"] == 720


async def test_a_new_claim_starts_with_no_turns_of_a_dead_session(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # A session that died without its end (a killed tab) may leave its list
    # behind until its TTL: the next claim of the account starts clean.
    user = uuid.uuid4()
    redis.lists[f"live:session:{user}:turns"] = [json.dumps(["user", "stale"])]
    assert await store.claim(_record(user), ttl_seconds=60) is True
    assert await store.turns(user) == []


async def test_a_release_takes_the_turns_with_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user = uuid.uuid4()
    record = _record(user, "a")
    assert await store.claim(record, ttl_seconds=60) is True
    await store.append_turns(user, [("user", "a")], ttl_seconds=30, max_rows=10)
    assert await store.release(user, "a") is True
    assert f"live:session:{user}:turns" not in redis.lists


# -- the standby (ADR-329) -------------------------------------------------------

_T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _awake_record() -> LiveSessionRecord:
    return replace(
        _record(uuid.uuid4()),
        started_at=_T0,
        awake_since=_T0,
        expires_at=_T0 + timedelta(minutes=10),
    )


def test_the_awake_time_is_the_sum_of_the_awake_stretches() -> None:
    record = _awake_record()
    assert record.awake_duration_seconds(_T0 + timedelta(seconds=90)) == 90
    asleep = record.entering_standby(_T0 + timedelta(seconds=90), conversation_id=None)
    assert asleep.in_standby and asleep.standbys == 1 and asleep.awake_seconds == 90
    # Time asleep counts for nothing.
    assert asleep.awake_duration_seconds(_T0 + timedelta(hours=3)) == 90
    awake = asleep.waking(_T0 + timedelta(hours=3))
    assert not awake.in_standby
    assert awake.awake_duration_seconds(_T0 + timedelta(hours=3, seconds=30)) == 120


def test_a_wake_shifts_the_cap_by_the_length_of_the_standby() -> None:
    # The cap measures time AWAKE: three hours asleep leave the ten minutes of
    # cap exactly where they were relative to the conversation.
    record = _awake_record()
    asleep = record.entering_standby(_T0 + timedelta(minutes=4), conversation_id=None)
    awake = asleep.waking(_T0 + timedelta(hours=3, minutes=4))
    assert awake.expires_at == record.expires_at + timedelta(hours=3)
    assert awake.awake_since == _T0 + timedelta(hours=3, minutes=4)


def test_every_conversation_a_wire_named_is_kept_once_in_order() -> None:
    record = _awake_record()
    first = record.entering_standby(_T0 + timedelta(minutes=1), conversation_id="conv_a")
    again = first.waking(_T0 + timedelta(minutes=2)).entering_standby(
        _T0 + timedelta(minutes=3), conversation_id="conv_b"
    )
    repeated = again.waking(_T0 + timedelta(minutes=4)).entering_standby(
        _T0 + timedelta(minutes=5), conversation_id="conv_b"
    )
    assert repeated.provider_conversation_ids == ("conv_a", "conv_b")
    assert repeated.standbys == 3


def test_a_record_asleep_lives_to_the_standby_bound_and_awake_to_its_cap() -> None:
    record = _awake_record()
    now = _T0 + timedelta(minutes=2)
    assert record.life_seconds(now, standby_max_seconds=3600) == record.remaining_life_seconds(now)
    asleep = record.entering_standby(now, conversation_id=None)
    assert asleep.standby_deadline(3600) == now + timedelta(seconds=3600)
    later = now + timedelta(minutes=10)
    # Asleep, the record outlives the standby bound by the closing grace —
    # whatever the cap says, which no longer runs.
    assert asleep.life_seconds(later, standby_max_seconds=3600) == (
        50 * 60 + LIVE_SESSION_RECORD_GRACE_SECONDS
    )
    # Past the bound the record still gets a positive life (it is about to go).
    assert asleep.life_seconds(now + timedelta(hours=5), standby_max_seconds=3600) >= 1


def test_the_standby_fields_round_trip_and_read_awake_when_absent() -> None:
    record = _awake_record().entering_standby(_T0 + timedelta(minutes=1), conversation_id="c1")
    assert LiveSessionRecord.from_json(record.to_json()) == record
    # A record written by the previous release has never slept.
    bare = json.loads(_awake_record().to_json())
    for key in ("standby_since", "awake_since", "awake_seconds", "standbys"):
        del bare[key]
    del bare["provider_conversation_ids"]
    older = LiveSessionRecord.from_json(json.dumps(bare))
    assert not older.in_standby and older.standbys == 0 and older.awake_seconds == 0
    assert older.awake_duration_seconds(_T0 + timedelta(seconds=5)) == 5
    assert older.provider_conversation_ids == ()


async def test_the_standby_drains_the_kept_turns_atomically(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # The rows are taken and removed in one command: a turn kept after the
    # drain belongs to the next connection, never relayed twice.
    user = uuid.uuid4()
    assert await store.claim(_record(user), ttl_seconds=600) is True
    await store.append_turns(user, [("user", "a"), ("assistant", "b")], ttl_seconds=600, max_rows=9)
    assert await store.drain_turns(user, max_rows=9) == [("user", "a"), ("assistant", "b")]
    assert await store.turns(user) == []
    assert await store.drain_turns(user, max_rows=9) == []
    await store.append_turns(user, [("user", "c")], ttl_seconds=600, max_rows=9)
    assert await store.drain_turns(user, max_rows=9) == [("user", "c")]


async def test_the_standby_relay_fates_are_kept_in_order_with_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    user = uuid.uuid4()
    record = _record(user, "a")
    assert await store.claim(record, ttl_seconds=600) is True
    await store.append_relay(user, "answered", None, ttl_seconds=500)
    await store.append_relay(user, "quota_blocked", "the recap", ttl_seconds=400)
    assert await store.relays(user) == [("answered", None), ("quota_blocked", "the recap")]
    assert redis.ttls[f"live:session:{user}:relays"] == 400
    # A rewrite of the record with a new life carries the fates along.
    assert await store.extend(replace(record, extensions=1), ttl_seconds=900) is True
    assert redis.ttls[f"live:session:{user}:relays"] == 900
    # A new session starts without the fates of a dead one; a release takes them.
    assert await store.release(user, "a") is True
    assert f"live:session:{user}:relays" not in redis.lists
    redis.lists[f"live:session:{user}:relays"] = [json.dumps(["failed", None])]
    assert await store.claim(_record(user, "b"), ttl_seconds=60) is True
    assert await store.relays(user) == []


async def test_an_extension_carries_the_lookup_budget_with_the_record(
    store: LiveSessionStore, redis: FakeRedis
) -> None:
    # The counter was given the record's life at the first lookup; a session
    # extended (or asleep) past it would find its counter reset to zero.
    user = uuid.uuid4()
    record = _record(user, "a")
    assert await store.claim(record, ttl_seconds=600) is True
    await store.consume_tool_budget(record.session_id, limit=5, ttl_seconds=600)
    assert await store.extend(replace(record, extensions=1), ttl_seconds=3000) is True
    assert redis.ttls[f"live_tools:{record.session_id}"] == 3000
