"""The recurrence-ledger seed against a real PostgreSQL (ADR-214 amendment).

Prod-like replay of the 2026-09-03 finding: the primary account had 183
``automation_run`` outcomes on the ``scheduler`` channel between 01:00 and
04:00 local (its 07:00-09:00 routines executed while their timezone was
still Asian) and 5 typed turns. The previous seed rebuilt the scheduler's
own metronome as the user's recurrences (email 27 days, event 26, weather
26, web_search 27); replayed alone, that night cluster LOCKS a daily habit
at 01:16. With the shared human predicate, the seed must keep every
signature within its typed days and the lock evaluation must stay silent.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.domains.agents.services.recurrence_ledger import evaluate_locks
from src.domains.habits.ledger_seed import seed_ledger_from_outcomes
from src.domains.habits.repository import HabitsRepository
from src.domains.product.models import ProductOutcome
from src.domains.users.models import User
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.integration

_TYPED_HOURS = {9, 11, 14, 16, 18}


class _FakeRedis:
    """NX-faithful in-memory double (the ledger is advisory Redis)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int, nx: bool = False) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    def scan_iter(self, match: str) -> object:
        prefix = match[:-1]

        async def _iter() -> object:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key

        return _iter()


def _lock_settings() -> SimpleNamespace:
    """The production defaults, read from settings — never re-declared."""
    return SimpleNamespace(
        recurrence_suggestion_enabled=True,
        recurrence_window_days=app_settings.recurrence_window_days,
        recurrence_min_distinct_days=app_settings.recurrence_min_distinct_days,
        recurrence_day_hours_cap=app_settings.recurrence_day_hours_cap,
        recurrence_ledger_max_entries=app_settings.recurrence_ledger_max_entries,
        recurrence_lock_min_occurrences=app_settings.recurrence_lock_min_occurrences,
        recurrence_lock_min_spread_days=app_settings.recurrence_lock_min_spread_days,
        recurrence_lock_r_min=app_settings.recurrence_lock_r_min,
        recurrence_lock_half_r_min=app_settings.recurrence_lock_half_r_min,
        recurrence_lock_half_agree_hours=app_settings.recurrence_lock_half_agree_hours,
        recurrence_shape_min_days=app_settings.recurrence_shape_min_days,
        recurrence_weekend_tolerance=app_settings.recurrence_weekend_tolerance,
        recurrence_weekly_min_same_dow=app_settings.recurrence_weekly_min_same_dow,
        recurrence_weekly_dow_fraction=app_settings.recurrence_weekly_dow_fraction,
    )


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email=f"habits-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Habits Owner",
        is_active=True,
        is_verified=True,
    )
    async_session.add(user)
    await async_session.flush()
    return user


def _outcome(
    user_id: uuid.UUID, at: datetime, *, channel: str, result_type: str, domain: str
) -> ProductOutcome:
    return ProductOutcome(
        user_id=user_id,
        run_id=uuid.uuid4().hex,
        result_type=result_type,
        domain=domain,
        execution_mode="pipeline",
        channel=channel,
        device_class="unknown",
        locale="fr",
        state="produced",
        evidence_level="E3",
        produced_at=at,
    )


async def _seed_prod_like_rows(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Scheduler outcomes over 4 domains at 01:00-04:00 Paris (23:00-02:00 UTC)
    across 26 nights, plus 5 typed web turns at daytime hours."""
    now = datetime.now(UTC)
    scheduler_rows = 0
    for night in range(26):
        base = (now - timedelta(days=night + 1)).replace(hour=23, minute=0, second=0, microsecond=0)
        batch = [(0, "email"), (30, "weather"), (60, "event"), (67, "web_search")]
        if night % 3 == 0:
            batch += [(90, "web_search"), (120, "place"), (150, "web_search")]
        for offset_min, domain in batch:
            session.add(
                _outcome(
                    user_id,
                    base + timedelta(minutes=offset_min),
                    channel="scheduler",
                    result_type="automation_run",
                    domain=domain,
                )
            )
            scheduler_rows += 1
    typed = [
        (2, 9, "email", "action"),
        (5, 14, "web_search", "answer"),
        (9, 18, "email", "action"),
        (12, 11, "event", "action"),
        (20, 16, "browser", "action"),
    ]
    for days_ago, hour, domain, result_type in typed:
        at = (now - timedelta(days=days_ago)).replace(hour=hour, minute=5, second=0, microsecond=0)
        session.add(_outcome(user_id, at, channel="web", result_type=result_type, domain=domain))
    await session.flush()
    return scheduler_rows, len(typed)


async def test_seed_keeps_lia_s_own_routines_out(async_session: AsyncSession, owner: User) -> None:
    scheduler_rows, typed_rows = await _seed_prod_like_rows(async_session, owner.id)
    assert scheduler_rows >= 100 and typed_rows == 5
    redis = _FakeRedis()

    with patch("src.infrastructure.cache.redis.get_redis_cache", new=AsyncMock(return_value=redis)):
        seeded = await seed_ledger_from_outcomes(
            async_session, owner.id, "Europe/Paris", _lock_settings()
        )

    # Only the typed domains are seeded, each with exactly its typed days.
    assert seeded == 4
    per_signature = {
        recurrence_store.signature_from_key(key, str(owner.id)): recurrence_store.parse_days(
            json.loads(value)
        )
        for key, value in redis.data.items()
    }
    assert set(per_signature) == {"email", "web_search", "event", "browser"}
    assert len(per_signature["email"]) == 2
    assert len(per_signature["web_search"]) == 1
    # Typed hours are the only hours present (UTC rows land at hour or hour+2
    # local depending on DST) — never the 01:00-04:00 night cluster.
    for days in per_signature.values():
        for hours in days.values():
            assert all(9 <= h <= 21 for h in hours), hours
    # And nothing locks: the night cluster alone WOULD lock daily at ~01:00 —
    # that is the false suggestion the shared predicate prevents.
    today = datetime.now(UTC).astimezone().date()
    for days in per_signature.values():
        assert evaluate_locks(days, today, _lock_settings()) is None


async def test_rhythm_run_source_reads_only_typed_outcomes(
    async_session: AsyncSession, owner: User
) -> None:
    """The rhythm repository reads the SAME predicate: the night cluster of
    scheduler outcomes contributes no hour to the user's activity."""
    await _seed_prod_like_rows(async_session, owner.id)
    repo = HabitsRepository(async_session)
    since = datetime.now(UTC) - timedelta(days=60)

    days = await repo.fetch_run_activity(owner.id, "Europe/Paris", since)

    assert len(days) == 5
    for hours in days.values():
        # Rows are inserted at UTC hours; Paris is UTC+1/+2.
        assert all(h - 2 in _TYPED_HOURS or h - 1 in _TYPED_HOURS for h in hours), hours
        assert all(count == 1 for count in hours.values())
    first_at, last_at = await repo.fetch_activity_bounds(owner.id)
    assert first_at is not None and last_at is not None
    assert (last_at - first_at).days >= 17
