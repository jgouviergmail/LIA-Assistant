"""Opening or touching an incident infers its partial unique index under any plan.

The upsert names the open incidents' partial unique index by its predicate. Bound as
a parameter (``WHERE status = $15``), the predicate can only be matched while
PostgreSQL plans the prepared statement with its values: once it plans it
generically, the arbiter index cannot be inferred and every self-check that opened
or touched an incident failed with « there is no unique or exclusion constraint
matching the ON CONFLICT specification » (dev API, 2026-10-22). Forcing the generic
plan makes that failure deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK, Incident
from src.domains.diagnostics.repository import DiagnosticsRepository

pytestmark = pytest.mark.integration


async def test_an_open_incident_is_opened_then_touched_under_a_generic_plan(
    async_session: AsyncSession,
) -> None:
    await async_session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    repo = DiagnosticsRepository(async_session)

    opened_id, created, _ = await repo.open_or_touch_incident(
        correlation_key="platform_egress",
        source=INCIDENT_SOURCE_SELF_CHECK,
        severity="warning",
        title="Egress degraded",
    )
    touched_id, created_again, _ = await repo.open_or_touch_incident(
        correlation_key="platform_egress",
        source=INCIDENT_SOURCE_SELF_CHECK,
        severity="critical",
        title="Egress cut",
    )

    assert (created, created_again) == (True, False)
    assert touched_id == opened_id
    row = await async_session.scalar(
        select(Incident).where(Incident.id == opened_id).execution_options(populate_existing=True)
    )
    assert row is not None and row.severity == "critical"
