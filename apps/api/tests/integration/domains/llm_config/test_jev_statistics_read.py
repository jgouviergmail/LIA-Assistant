"""The statistics read on a real PostgreSQL: exact sums over a window of UTC days (ADR-374)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import now_utc
from src.domains.chat.models import TokenUsageLog
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_statistics_read import read_jev_statistics
from src.domains.llm_config.jev_statistics_repository import (
    JevStatisticsBatch,
    JevStatisticsRepository,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v1/admin/llm-config/jev/statistics"
EMAIL = JevUsage.EMAIL_CLASSIFICATION
OBSERVER = JevUsage.OBSERVE_MEMORY


def _usage(response: Any, usage: JevUsage) -> Any:
    return next(item for item in response.usages if item.usage is usage)


async def test_the_window_sums_exactly_what_was_counted_in_it(async_session: AsyncSession) -> None:
    session = async_session
    before = await read_jev_statistics(session, days=7)
    today = now_utc().date()
    old = today - timedelta(days=7)  # the day just outside a 7-day window

    batch = JevStatisticsBatch()
    batch.judgements[(today, EMAIL.value, "priority", 80)] += 3
    batch.judgements[(today - timedelta(days=6), EMAIL.value, "priority", 80)] += 2
    batch.judgements[(old, EMAIL.value, "priority", 80)] += 100
    batch.outcomes[(today, EMAIL.value, "classified")] += 4
    batch.outcomes[(old, EMAIL.value, "classified")] += 100
    batch.agreement[(today, OBSERVER.value, "empty", 90, False)] += 5
    await JevStatisticsRepository(session).upsert(batch)

    slot = JEV_USAGES[EMAIL].llm_type
    inside = datetime.combine(today, time(12), tzinfo=UTC)
    outside = datetime.combine(old, time(12), tzinfo=UTC)
    for created_at, latency, cost in (
        (inside, 100, "0.001"),
        (inside, 300, "0.002"),
        (outside, 9, "9"),
    ):
        session.add(
            TokenUsageLog(
                user_id=uuid4(),
                run_id=f"stats-{uuid4().hex}",
                node_name="jev_email_classification",
                model_name="jev-1.14.0",
                cost_eur=Decimal(cost),
                latency_ms=latency,
                llm_type=slot,
                created_at=created_at,
            )
        )
    await session.flush()

    after = await read_jev_statistics(session, days=7)
    email, email_before = _usage(after, EMAIL), _usage(before, EMAIL)
    priority = next(gate for gate in email.gates if gate.key == "priority")
    priority_before = next(gate for gate in email_before.gates if gate.key == "priority")
    assert priority.buckets[80] - priority_before.buckets[80] == 5
    assert email.outcomes.get("classified", 0) - email_before.outcomes.get("classified", 0) == 4
    assert email.calls - email_before.calls == 2
    assert round(email.cost_eur - email_before.cost_eur, 6) == 0.003
    if email_before.calls == 0:
        assert email.latency_p50_ms == 200
    observer = _usage(after, OBSERVER)
    rows = {(r.verdict, r.bucket, r.proposed): r.count for r in observer.agreement or []}
    rows_before = {
        (r.verdict, r.bucket, r.proposed): r.count for r in _usage(before, OBSERVER).agreement or []
    }
    assert rows.get(("empty", 90, False), 0) - rows_before.get(("empty", 90, False), 0) == 5
    assert _usage(after, JevUsage.MEETING_TEMPLATE).agreement is None


async def test_only_an_administrator_reads_the_statistics(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _ = authenticated_client
    assert (await client.get(ENDPOINT)).status_code == 403


async def test_an_anonymous_request_is_refused(async_client: AsyncClient) -> None:
    assert (await async_client.get(ENDPOINT)).status_code == 401


async def test_the_window_is_bounded(admin_client: tuple[AsyncClient, User]) -> None:
    client, _ = admin_client
    ok = await client.get(ENDPOINT, params={"days": 30})
    assert ok.status_code == 200 and ok.json()["days"] == 30
    assert len(ok.json()["usages"]) == len(JEV_USAGES)
    for days in (0, 91, "x"):
        assert (await client.get(ENDPOINT, params={"days": days})).status_code == 422
