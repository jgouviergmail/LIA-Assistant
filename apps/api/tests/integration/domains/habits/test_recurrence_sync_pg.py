"""A recurring need's life on a real PostgreSQL, through the real nightly run (ADR-375).

What the ADR-214 hour lock could not learn, replayed end to end:

- a domain asked on many days at hours that WANDER is a need — the lock wanted
  one hour, and one off-hour ask a week defeated it;
- it is learned by the nightly recompute alone, no chat turn;
- at the automation bar it opens ONE proposal, refreshed (never duplicated) the
  next night and withdrawn the night the need lapses or the person pauses it;
- an expired ledger demotes the ACTIVE need; the person's paused and blocked
  rows survive it, and a blocked need is never refreshed;
- an unreadable ledger changes nothing, and an open proposal is held.

The ledger is an NX-faithful in-memory double (advisory Redis); the rows, the
statuses, the proposals, the ports and the recompute are real.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.domains.agents.effects import routine_reads
from src.domains.habits import usage_ports
from src.domains.habits.models import (
    HabitKind,
    HabitProposal,
    HabitStatus,
    ProposalKind,
    ProposalStatus,
    UserHabit,
)
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.service import HabitsService
from src.domains.habits.usage_refresh import refresh_usage
from src.domains.heartbeat import feedback_summary
from src.domains.users.models import User
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.integration

TZ = ZoneInfo("Europe/Paris")
#: Hours a real person asks at: nothing a lock could hold on.
WANDERING = (8.66, 13.16, 19.5, 10.0, 21.25, 7.9, 16.4)


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> Any:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> int:
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    def scan_iter(self, match: str) -> Any:
        prefix = match[:-1]

        async def _iter() -> Any:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key

        return _iter()


@pytest.fixture(autouse=True)
def _real_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage_ports, "_PORTS", usage_ports._Ports())
    usage_ports.install_routine_reads_reader(routine_reads.read_routine_run_domains)
    usage_ports.install_proactive_feedback_reader(feedback_summary.read_proactive_feedback)


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"habits-sync-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Habits Sync Owner",
        is_active=True,
        is_verified=True,
    )
    user.timezone = "Europe/Paris"
    user.language = "fr"
    user.habits_enabled = True
    async_session.add(user)
    await async_session.flush()
    return user


def _today() -> date:
    return datetime.now(TZ).date()


def _asked(today: date, first: int, last: int) -> dict[date, list[float]]:
    return {
        today - timedelta(days=k): [WANDERING[k % len(WANDERING)]] for k in range(first, last + 1)
    }


def _ledger(
    redis: _FakeRedis, user_id: uuid.UUID, domain: str, days: dict[date, list[float]]
) -> None:
    payload = {"days": {d.isoformat(): h for d, h in days.items()}, "origin": "live"}
    redis.data[recurrence_store.redis_key(str(user_id), domain)] = json.dumps(payload)


async def _active(session: AsyncSession, user_id: uuid.UUID, today: date, days: int) -> None:
    """The person used LIA on these days (the rollup the previous nights banked)."""
    await HabitsRepository(session).upsert_activity_days(
        user_id, {today - timedelta(days=k): {9: 1} for k in range(1, days + 1)}
    )


async def _needs(session: AsyncSession, user_id: uuid.UUID) -> list[UserHabit]:
    result = await session.execute(
        select(UserHabit).where(
            UserHabit.user_id == user_id, UserHabit.kind == HabitKind.RECURRING_REQUEST.value
        )
    )
    return list(result.scalars().all())


async def _proposals(session: AsyncSession, user_id: uuid.UUID) -> list[HabitProposal]:
    result = await session.execute(
        select(HabitProposal)
        .where(HabitProposal.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def _patch(redis: _FakeRedis | None) -> Any:
    return patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis))


async def _night(session: AsyncSession, owner: User) -> Any:
    outcome = await refresh_usage(session, owner, settings=app_settings, now=datetime.now(UTC))
    await session.flush()
    return outcome


async def test_a_need_asked_at_wandering_hours_is_learned_by_the_nightly_alone(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = _today()
    _ledger(redis, owner.id, "weather", _asked(today, 1, 21))
    await _active(async_session, owner.id, today, 21)
    await async_session.flush()

    with _patch(redis):
        await HabitsService(async_session).recompute_user_profile(owner, force=True)
    await async_session.flush()

    [need] = await _needs(async_session, owner.id)
    assert (need.key, need.status) == ("weather", HabitStatus.ACTIVE.value)
    assert (need.payload["version"], need.payload["cadence"]) == (2, "daily")
    assert need.payload["at_automation_bar"] is True
    assert need.last_observed_at.astimezone(TZ).date() == today - timedelta(days=1)
    [proposal] = await _proposals(async_session, owner.id)
    assert (proposal.kind, proposal.key) == (ProposalKind.AUTOMATE_NEED.value, "weather")
    assert proposal.status == ProposalStatus.OPEN.value
    assert proposal.payload["minute"] in (0, 15, 30, 45)


async def test_the_proposal_is_refreshed_never_duplicated_and_withdrawn_when_the_need_lapses(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = _today()
    _ledger(redis, owner.id, "weather", _asked(today, 1, 21))
    await _active(async_session, owner.id, today, 21)
    with _patch(redis):
        await _night(async_session, owner)
        [first] = await _proposals(async_session, owner.id)
        # One more ask: the facts move, the row stays the same row.
        _ledger(redis, owner.id, "weather", _asked(today, 0, 21))
        second = await _night(async_session, owner)
        [again] = await _proposals(async_session, owner.id)
        assert again.id == first.id and again.status == ProposalStatus.OPEN.value
        assert second.proposals.transitions.get(("automate_need", "opened")) is None

        # The ledger expires (its TTL): the need lapses, its proposal goes with it.
        redis.data.clear()
        lapsed = await _night(async_session, owner)
    assert await _needs(async_session, owner.id) == []
    assert await _proposals(async_session, owner.id) == []
    assert lapsed.recurring.demoted == 1
    assert lapsed.proposals.transitions == {("automate_need", "withdrawn"): 1}


@pytest.mark.parametrize("status", [HabitStatus.PAUSED.value, HabitStatus.BLOCKED.value])
async def test_the_persons_own_statuses_survive_the_ledger_and_silence_the_proposal(
    async_session: AsyncSession, owner: User, status: str
) -> None:
    redis = _FakeRedis()
    today = _today()
    _ledger(redis, owner.id, "weather", _asked(today, 1, 21))
    await _active(async_session, owner.id, today, 21)
    repo = HabitsRepository(async_session)
    with _patch(redis):
        await _night(async_session, owner)
        [row] = await _needs(async_session, owner.id)
        learned = dict(row.payload)
        await repo.set_status(row, status)
        await async_session.flush()

        # The person said stop: the open proposal leaves the next night.
        await _night(async_session, owner)
        assert await _proposals(async_session, owner.id) == []

        # An expired ledger never removes what the person decided…
        redis.data.clear()
        await _night(async_session, owner)
        [kept] = await _needs(async_session, owner.id)
        assert (kept.id, kept.status) == (row.id, status)

        # …and the need returning refreshes a paused row, never a blocked one.
        _ledger(redis, owner.id, "weather", _asked(today, 1, 14))
        await _night(async_session, owner)
    await async_session.refresh(kept)
    assert (kept.id, kept.status) == (row.id, status)
    if status == HabitStatus.PAUSED.value:
        assert kept.payload["distinct_days"] == 14
    else:
        assert kept.payload == learned
    assert await _proposals(async_session, owner.id) == []


async def test_an_unreadable_ledger_changes_nothing_and_holds_the_proposal(
    async_session: AsyncSession, owner: User
) -> None:
    redis = _FakeRedis()
    today = _today()
    _ledger(redis, owner.id, "weather", _asked(today, 1, 21))
    await _active(async_session, owner.id, today, 21)
    with _patch(redis):
        await _night(async_session, owner)
    [need] = await _needs(async_session, owner.id)
    payload = dict(need.payload)

    with _patch(None):
        outcome = await _night(async_session, owner)

    assert outcome.recurring.skipped is True
    assert outcome.proposals.transitions == {("automate_need", "held"): 1}
    [kept] = await _needs(async_session, owner.id)
    assert (kept.id, kept.payload) == (need.id, payload)
    [proposal] = await _proposals(async_session, owner.id)
    assert proposal.status == ProposalStatus.OPEN.value
