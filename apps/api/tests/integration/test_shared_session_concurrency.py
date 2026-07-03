"""Integration reproduction of shared-AsyncSession concurrency (audit A5a, N-206/N-209).

SQLAlchemy forbids concurrent operations on a single ``AsyncSession``
("another operation is in progress"). Two production paths violated this:

- ``HealthMetricsService.compute_overview``: one ``compute_kind_summary`` per
  health kind, gathered concurrently on the service's shared session.
- ``heartbeat.ContextAggregator.aggregate``: 10 fetchers gathered with
  ``return_exceptions=True``, 8 of them querying the shared ``self._db`` —
  concurrency errors are silently converted into ``failed_sources``, so each
  heartbeat non-deterministically loses context sources.

These tests run against a real PostgreSQL database: the failure mode is a
driver-level property (one asyncpg connection, interleaved queries) that
mocks cannot reproduce.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.health_metrics.kinds import HEALTH_KINDS
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.heartbeat.context_aggregator import ContextAggregator

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pooled_sessionmaker(async_engine, test_database_url: str, monkeypatch):
    """Production-like sessions + app-global ``AsyncSessionLocal`` redirect.

    Two things the default ``async_session`` fixture cannot provide:

    - Its engine uses ``StaticPool``: the single pooled connection is already
      established, so a FRESH session acquires it synchronously (no await →
      no connection-provisioning race) and the asyncpg dialect's internal
      mutex then silently serializes interleaved queries. That masks the
      production failure mode entirely. A real pooled engine reproduces it:
      concurrent first-queries on one fresh session race in
      ``_connection_for_bind`` → ``InvalidRequestError``.
    - ``get_db_context()`` (per-fetcher session pattern) resolves the
      module-global ``AsyncSessionLocal`` at call time; in the test process
      that global targets the ``.env.test`` URL, so it is repointed at the
      test database. (Depends on ``async_engine`` so the schema exists.)
    """
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from src.infrastructure.database import session as session_module

    monkeypatch.setattr(session_module, "AsyncSessionLocal", maker)
    yield maker
    await engine.dispose()


async def test_health_overview_survives_kind_fanout(pooled_sessionmaker) -> None:
    """compute_overview must not issue concurrent queries on its shared session.

    Before the fix: the per-kind gather races the fresh session's connection
    provisioning ("This session is provisioning a new connection; concurrent
    operations are not permitted").
    """
    async with pooled_sessionmaker() as session:
        service = HealthMetricsService(session)

        overview = await service.compute_overview(uuid4())

    assert set(overview.keys()) == set(HEALTH_KINDS.keys())


async def test_heartbeat_aggregator_loses_no_source_to_session_concurrency(
    test_user,
    pooled_sessionmaker,
) -> None:
    """No heartbeat source may fail because of session-sharing concurrency.

    The user has no connectors configured, so every fetcher stops after its
    initial database reads — network-hermetic, yet 8 fetchers still issue
    their first SELECTs concurrently. Before the fix those queries share one
    fresh session and ``return_exceptions=True`` converts the resulting
    concurrency errors into silent ``failed_sources``.
    """
    async with pooled_sessionmaker() as session:
        aggregator = ContextAggregator(session)

        context = await aggregator.aggregate(user_id=test_user.id, user=test_user)

    assert context.failed_sources == [], (
        "heartbeat sources lost to shared-session concurrency: " f"{context.failed_sources}"
    )
