"""Real SQL/Redis fixtures for durable conversation execution boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.conversation_execution import RunAdmission
from src.domains.conversations import cleanup_port, legacy_reset
from src.infrastructure.conversation_cleanup_runtime import NativeRuntimeCleanup
from src.infrastructure.streaming import live_binding, run_admission, runtime_redis
from tests.fixtures.persisted_runtimes import persist_runtime_targets


@pytest.fixture
def legacy_reset_runtime(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Install the startup adapter and give each cleanup operation its own test session."""
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            yield db
            await db.commit()

    monkeypatch.setattr(cleanup_port, "_runtime_cleanup", NativeRuntimeCleanup())
    monkeypatch.setattr(legacy_reset, "AsyncSessionLocal", factory)
    monkeypatch.setattr(live_binding, "get_db_context", session)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path / "attachments"))


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Use only the suite's disposable Redis; failures never skip the contract."""
    async with Redis.from_url(str(settings.redis_url), decode_responses=True) as client:
        await client.ping()
        yield client


@pytest_asyncio.fixture
async def reserved(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> RunAdmission:
    """Replace connection composition alone; every SQL transition remains production code."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(run_admission, "get_db_context", session)
    monkeypatch.setattr(runtime_redis, "get_db_context", session)
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    result = await run_admission.reserve_execution(
        target,
        run_id=str(uuid4()),
        stream_id=str(uuid4()),
        relayed=False,
    )
    assert isinstance(result, RunAdmission)
    return result
