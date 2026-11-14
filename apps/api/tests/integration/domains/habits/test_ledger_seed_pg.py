"""The recurrence-ledger seed against a real PostgreSQL (ADR-214 amendment, ADR-375).

Prod-like replay of the 2026-09-03 finding: the primary account had 183
``automation_run`` outcomes on the ``scheduler`` channel between 01:00 and
04:00 local (its 07:00-09:00 routines executed while their timezone was
still Asian) and 5 typed turns. The previous seed rebuilt the scheduler's
own metronome as the user's recurrences (email 27 days, event 26, weather
26, web_search 27); replayed alone, that night cluster would read as four
recurring NEEDS. With the shared human predicate, the seed must keep every
signature within its typed days, and no need may be read from it.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.domains.habits.ledger_seed import seed_ledger_from_outcomes
from src.domains.habits.needs import NeedThresholds
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.usage_observations import LedgerView, needs_from_ledger
from src.domains.product.models import ProductOutcome
from src.domains.users.models import User
from src.infrastructure.cache import recurrence_store
from tests.fixtures.conversation_executions import redis_client as redis_client

pytestmark = pytest.mark.integration

_TYPED_HOURS = {9, 11, 14, 16, 18}


def _seed_settings() -> SimpleNamespace:
    """The production defaults, read from settings — never re-declared."""
    return SimpleNamespace(
        habits_enabled=True,
        recurrence_window_days=app_settings.recurrence_window_days,
        recurrence_day_hours_cap=app_settings.recurrence_day_hours_cap,
        recurrence_ledger_max_entries=app_settings.recurrence_ledger_max_entries,
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


async def test_seed_keeps_lia_s_own_routines_out(
    async_session: AsyncSession, owner: User, redis_client: Redis
) -> None:
    scheduler_rows, typed_rows = await _seed_prod_like_rows(async_session, owner.id)
    assert scheduler_rows >= 100 and typed_rows == 5
    owner_key = str(owner.id)
    pattern = recurrence_store.user_key_pattern(owner_key)
    per_signature = {}

    try:
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=redis_client),
        ):
            seeded = await seed_ledger_from_outcomes(
                async_session, owner.id, "Europe/Paris", _seed_settings()
            )
        async for key in redis_client.scan_iter(match=pattern):
            value = await redis_client.get(key)
            assert isinstance(value, str)
            per_signature[recurrence_store.signature_from_key(key, owner_key)] = (
                recurrence_store.parse_days(json.loads(value))
            )
    finally:
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        await redis_client.delete(recurrence_store.writer_key(owner_key), *keys)

    # Only the typed domains are seeded, each with exactly its typed days.
    assert seeded == 4
    assert set(per_signature) == {"email", "web_search", "event", "browser"}
    assert len(per_signature["email"]) == 2
    assert len(per_signature["web_search"]) == 1
    # Typed hours are the only hours present (UTC rows land at hour or hour+2
    # local depending on DST) — never the 01:00-04:00 night cluster.
    for days in per_signature.values():
        for hours in days.values():
            assert all(9 <= h <= 21 for h in hours), hours
    # And no need is read: the night cluster alone WOULD read as four daily
    # needs — the false proposal the shared predicate prevents.
    ledger = LedgerView(readable=True, days_by_domain=per_signature, intents={})
    needs = needs_from_ledger(
        ledger,
        active_days=typed_rows,
        today=datetime.now(UTC).date(),
        thresholds=NeedThresholds.from_settings(app_settings),
    )
    assert needs == ()


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
