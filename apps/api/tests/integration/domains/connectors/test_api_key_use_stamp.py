"""Reading an API key leaves no lock in its caller's transaction (ADR-304).

Proved on a real PostgreSQL server, because both defects are properties of the
database that no mock reproduces: ``get_api_key_credentials`` FLUSHED a new
metadata dict on its caller's session — an UPDATE, so the connector row stayed
locked until that caller's transaction ended (a whole chat turn, a whole
telephony dial) — and the dict was recomputed in Python from what the caller
had loaded, so a concurrent writer of another key was overwritten.

Every row here is REALLY committed (the per-test SAVEPOINT isolation hides a
row from every other connection, and a lock is only visible across two), and
removed with its account at the end.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.constants import CONNECTOR_USE_STAMP_LOCK_TIMEOUT_MS
from src.core.security import encrypt_data
from src.domains.connectors.api_key_use import stamp_api_key_use
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User

pytestmark = pytest.mark.integration

Maker = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> AsyncIterator[tuple[Maker, str]]:
    """A sessionmaker whose writes really commit, and the account's clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"api_key_stamp_{uuid4().hex}@example.com"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed(maker: Maker, email: str) -> tuple[UUID, UUID]:
    """An account with an active API-key connector carrying another metadata key."""
    async with maker() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.OPENWEATHERMAP,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypt_data(json.dumps({"api_key": "k" * 32})),
            connector_metadata={"agent_config_hash": "before"},
        )
        session.add(connector)
        await session.commit()
        return UUID(str(user.id)), UUID(str(connector.id))


async def _metadata(maker: Maker, connector_id: UUID) -> dict[str, Any]:
    async with maker() as session:
        row = await session.execute(
            select(Connector.connector_metadata).where(Connector.id == connector_id)
        )
        return dict(row.scalar_one() or {})


async def test_reading_the_key_leaves_the_row_unlocked(committed: tuple[Maker, str]) -> None:
    maker, marker = committed
    user_id, connector_id = await _seed(maker, marker)

    async with maker() as caller:
        credentials = await ConnectorService(caller).get_api_key_credentials(
            user_id, ConnectorType.OPENWEATHERMAP
        )
        assert credentials is not None
        # The caller's transaction is still open. Before ADR-304 it held the
        # row, and NOWAIT failed at once for any other writer.
        async with maker() as other:
            await other.execute(
                select(Connector.id)
                .where(Connector.id == connector_id)
                .with_for_update(nowait=True)
            )
            await other.rollback()
        await caller.rollback()

    assert "last_used_at" in await _metadata(maker, connector_id)


async def test_the_stamp_keeps_a_key_written_meanwhile(committed: tuple[Maker, str]) -> None:
    maker, marker = committed
    user_id, connector_id = await _seed(maker, marker)

    async with maker() as caller:
        service = ConnectorService(caller)
        # The caller loads the row; somebody else then writes another key.
        await service.repository.get_by_user_and_type(user_id, ConnectorType.OPENWEATHERMAP)
        async with maker() as writer:
            await writer.execute(
                text(
                    "UPDATE connectors SET metadata = metadata || "
                    "jsonb_build_object('agent_config_hash', 'after') WHERE id = :id"
                ),
                {"id": connector_id},
            )
            await writer.commit()
        await service.get_api_key_credentials(user_id, ConnectorType.OPENWEATHERMAP)
        await caller.commit()

    metadata = await _metadata(maker, connector_id)
    # The stamp merged its key into what was STORED, never into a stale copy.
    assert metadata["agent_config_hash"] == "after"
    assert datetime.fromisoformat(metadata["last_used_at"]) <= datetime.now(UTC)


async def test_a_busy_row_skips_the_stamp_within_its_bound(committed: tuple[Maker, str]) -> None:
    maker, marker = committed
    _user_id, connector_id = await _seed(maker, marker)

    async with maker() as holder:
        locked = await holder.execute(
            select(Connector.id).where(Connector.id == connector_id).with_for_update()
        )
        assert locked.scalar_one() == connector_id
        started = time.monotonic()
        await stamp_api_key_use(connector_id)  # must neither raise nor hang
        waited = time.monotonic() - started
        await holder.rollback()

    assert waited < CONNECTOR_USE_STAMP_LOCK_TIMEOUT_MS / 1000 + 2.0
    assert "last_used_at" not in await _metadata(maker, connector_id)
