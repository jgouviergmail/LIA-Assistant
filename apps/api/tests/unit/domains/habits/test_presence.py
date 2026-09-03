"""Reading presence — the fourth rhythm source (ADR-214 amendment 2026-09-03).

Owner decision: an app opening (visibility ping) and a thumb on a
notification count as presence; a notification being SENT never does. What
must hold: one banked hour per local hour (two workers, one write), the
user's LOCAL date and hour (timezone changes, DST), the gates (master flag,
user preference, visibility flag — feedback passes without the latter), and
fail-open on Redis.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.habits import presence
from src.domains.habits.presence import (
    forget_user,
    hour_key,
    last_key,
    last_presence_at,
    last_seen_at,
    presence_allowed,
    record_presence,
)

pytestmark = pytest.mark.unit


class _FakeRedis:
    """NX-faithful double with scan/delete for the forget surface."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.fail = False

    async def set(self, key: str, value: str, ex: int, nx: bool = False) -> bool | None:
        if self.fail:
            raise ConnectionError("down")
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("down")
        return self.data.get(key)

    def scan_iter(self, match: str) -> object:
        prefix = match[:-1]

        async def _iter() -> object:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key.encode()

        return _iter()

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed


def _user(tz: str = "Europe/Paris", habits_enabled: bool = True, last_login: Any = None) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(), timezone=tz, habits_enabled=habits_enabled, last_login=last_login
    )


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "habits_enabled": True,
        "habits_presence_enabled": True,
        "habits_presence_last_ttl_days": 30,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def repo() -> MagicMock:
    instance = MagicMock()
    instance.bump_activity_hour = AsyncMock()
    return instance


@pytest.fixture(autouse=True)
def _wire(redis: _FakeRedis, repo: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(presence, "settings", _settings())
    monkeypatch.setattr(presence, "HabitsRepository", lambda db: repo)
    monkeypatch.setattr(presence, "_redis_or_none", AsyncMock(return_value=redis))


class TestGates:
    def test_visibility_needs_all_three_switches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert presence_allowed(_user(), "visibility") is True
        monkeypatch.setattr(presence, "settings", _settings(habits_presence_enabled=False))
        assert presence_allowed(_user(), "visibility") is False
        monkeypatch.setattr(presence, "settings", _settings(habits_enabled=False))
        assert presence_allowed(_user(), "visibility") is False
        monkeypatch.setattr(presence, "settings", _settings())
        assert presence_allowed(_user(habits_enabled=False), "visibility") is False

    def test_feedback_counts_even_with_the_visibility_flag_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A thumb is an explicit human act (owner decision): it does not
        wait for the visibility flag — but it still respects habits gates."""
        monkeypatch.setattr(presence, "settings", _settings(habits_presence_enabled=False))
        assert presence_allowed(_user(), "feedback") is True
        assert presence_allowed(_user(habits_enabled=False), "feedback") is False

    async def test_disabled_signal_writes_nothing(
        self, repo: MagicMock, redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(presence, "settings", _settings(habits_presence_enabled=False))
        outcome = await record_presence(MagicMock(), _user(), kind="visibility")
        assert outcome == "disabled"
        repo.bump_activity_hour.assert_not_awaited()
        assert redis.data == {}


class TestBanking:
    async def test_first_signal_of_the_hour_is_banked_at_the_local_hour(
        self, repo: MagicMock, redis: _FakeRedis
    ) -> None:
        user = _user("Europe/Paris")
        at = datetime(2026, 9, 3, 12, 20, tzinfo=UTC)  # 14:20 Paris (CEST)
        outcome = await record_presence(MagicMock(), user, kind="visibility", at=at)
        assert outcome == "banked"
        repo.bump_activity_hour.assert_awaited_once_with(user.id, date(2026, 9, 3), 14)
        assert hour_key(user.id, date(2026, 9, 3), 14) in redis.data
        assert redis.data[last_key(user.id)] == at.isoformat()

    async def test_second_signal_in_the_same_local_hour_is_throttled(self, repo: MagicMock) -> None:
        user = _user()
        first = datetime(2026, 9, 3, 12, 5, tzinfo=UTC)
        second = datetime(2026, 9, 3, 12, 50, tzinfo=UTC)
        assert await record_presence(MagicMock(), user, kind="visibility", at=first) == "banked"
        assert await record_presence(MagicMock(), user, kind="feedback", at=second) == "throttled"
        assert repo.bump_activity_hour.await_count == 1

    async def test_a_timezone_change_dates_the_signal_in_the_new_zone(
        self, repo: MagicMock
    ) -> None:
        """23:30 UTC is 07:30 the NEXT day in Asia/Makassar and 01:30 the next
        day in Paris — the banked day follows the user's wall clock."""
        at = datetime(2026, 9, 3, 23, 30, tzinfo=UTC)
        makassar = _user("Asia/Makassar")
        await record_presence(MagicMock(), makassar, kind="visibility", at=at)
        repo.bump_activity_hour.assert_awaited_with(makassar.id, date(2026, 9, 4), 7)
        paris = _user("Europe/Paris")
        await record_presence(MagicMock(), paris, kind="visibility", at=at)
        repo.bump_activity_hour.assert_awaited_with(paris.id, date(2026, 9, 4), 1)

    async def test_dst_fallback_hour_is_a_real_local_hour(self, repo: MagicMock) -> None:
        """2026-10-25 01:30 UTC is 02:30 CET after the fall-back: still hour 2,
        never 25 or a negative — the JSON key stays 0-23 by construction."""
        at = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
        user = _user("Europe/Paris")
        await record_presence(MagicMock(), user, kind="visibility", at=at)
        repo.bump_activity_hour.assert_awaited_with(user.id, date(2026, 10, 25), 2)

    async def test_redis_down_still_banks_the_hour(
        self, repo: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(presence, "_redis_or_none", AsyncMock(return_value=None))
        outcome = await record_presence(MagicMock(), _user(), kind="feedback")
        assert outcome == "banked"
        repo.bump_activity_hour.assert_awaited_once()

    async def test_redis_error_mid_call_is_fail_open(
        self, repo: MagicMock, redis: _FakeRedis
    ) -> None:
        redis.fail = True
        outcome = await record_presence(MagicMock(), _user(), kind="visibility")
        assert outcome == "banked"
        repo.bump_activity_hour.assert_awaited_once()


class TestLastSeen:
    async def test_last_presence_is_read_back_as_aware_utc(self, redis: _FakeRedis) -> None:
        user = _user()
        at = datetime(2026, 9, 3, 12, 20, tzinfo=UTC)
        await record_presence(MagicMock(), user, kind="visibility", at=at)
        assert await last_presence_at(user.id) == at

    async def test_last_seen_is_the_later_of_login_and_presence(self, redis: _FakeRedis) -> None:
        user = _user(last_login=datetime(2026, 8, 1, tzinfo=UTC))
        assert await last_seen_at(user) == datetime(2026, 8, 1, tzinfo=UTC)
        at = datetime(2026, 9, 3, 12, 20, tzinfo=UTC)
        await record_presence(MagicMock(), user, kind="feedback", at=at)
        assert await last_seen_at(user) == at

    async def test_naive_last_login_is_treated_as_utc(self) -> None:
        user = _user(last_login=datetime(2026, 8, 1, 10, 0))
        assert await last_seen_at(user) == datetime(2026, 8, 1, 10, 0, tzinfo=UTC)

    async def test_nothing_known_is_none(self) -> None:
        assert await last_seen_at(_user()) is None

    async def test_redis_down_reads_as_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(presence, "_redis_or_none", AsyncMock(return_value=None))
        assert await last_presence_at(uuid.uuid4()) is None


class TestForget:
    async def test_forget_removes_hours_and_marker_of_that_user_only(
        self, redis: _FakeRedis
    ) -> None:
        user, other = _user(), _user()
        at = datetime(2026, 9, 3, 12, 20, tzinfo=UTC)
        await record_presence(MagicMock(), user, kind="visibility", at=at)
        await record_presence(MagicMock(), other, kind="visibility", at=at)
        deleted = await forget_user(redis, user.id)
        assert deleted == 2
        assert set(redis.data) == {hour_key(other.id, date(2026, 9, 3), 14), last_key(other.id)}


def test_keys_belong_to_the_presence_learning_family() -> None:
    """ADR-260: a reset must never wipe them; account deletion must."""
    from src.infrastructure.cache.key_families import is_reset_purgeable, is_user_scoped

    uid = uuid.uuid4()
    for key in (hour_key(uid, date(2026, 9, 3), 14), last_key(uid)):
        assert is_reset_purgeable(key) is False
        assert is_user_scoped(key) is True


@pytest.mark.parametrize("hour", [-1, 24])
async def test_repository_refuses_an_out_of_range_hour(hour: int) -> None:
    from src.domains.habits.repository import HabitsRepository

    with pytest.raises(ValueError):
        await HabitsRepository(MagicMock()).bump_activity_hour(uuid.uuid4(), date(2026, 9, 3), hour)


async def test_repository_bump_is_a_server_side_upsert() -> None:
    """Never SELECT → increment → flush: the statement itself carries the
    ON CONFLICT arithmetic (GREATEST(existing, 1))."""
    from src.domains.habits.repository import HabitsRepository

    db = MagicMock()
    db.execute = AsyncMock()
    await HabitsRepository(db).bump_activity_hour(uuid.uuid4(), date(2026, 9, 3), 14)
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "ON CONFLICT ON CONSTRAINT uq_user_activity_days_user_date" in compiled
    assert "jsonb_set" in compiled and "GREATEST" in compiled and "'14'" in compiled
