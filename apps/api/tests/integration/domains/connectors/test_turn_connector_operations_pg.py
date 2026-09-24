"""A chat turn's connector operations leave no transaction open (ADR-304).

Proved on a real PostgreSQL session, because « no transaction open » is a
property of the session and the server, not of any mock: the turn's session
used to keep the transaction its first credential read began for the rest of
the turn — every tool's provider calls included — and a client's token refresh
ran inside it, under the tools' lock.

Every row here is REALLY committed and removed with its account at the end.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security import encrypt_data
from src.domains.agents.dependencies import ToolDependencies
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.session_scope import connector_unit_of_work, owns_session
from src.domains.users.models import User

pytestmark = pytest.mark.integration

Maker = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def committed(async_engine: Any, test_database_url: str) -> AsyncIterator[tuple[Maker, str]]:
    """A sessionmaker whose writes really commit, and the account's clean-up."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"turn_ops_{uuid4().hex}@example.com"
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email == marker))
        await session.commit()
    await engine.dispose()


async def _seed(maker: Maker, email: str) -> tuple[UUID, UUID]:
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
            connector_metadata={},
        )
        session.add(connector)
        await session.commit()
        return UUID(str(user.id)), UUID(str(connector.id))


async def test_an_operation_leaves_the_turn_session_without_a_transaction(
    committed: tuple[Maker, str],
) -> None:
    maker, marker = committed
    user_id, connector_id = await _seed(maker, marker)

    async with maker() as turn:
        service = await ToolDependencies(db_session=turn).get_connector_service()
        assert await service.is_connector_active(user_id, ConnectorType.OPENWEATHERMAP)
        credentials = await service.get_api_key_credentials(user_id, ConnectorType.OPENWEATHERMAP)
        assert credentials is not None
        # The tool now calls its provider: nothing may be held meanwhile.
        assert not turn.in_transaction(), "the turn kept its transaction open"
        async with maker() as other:
            await other.execute(
                select(Connector.id)
                .where(Connector.id == connector_id)
                .with_for_update(nowait=True)
            )
            await other.rollback()


async def test_a_clients_own_writes_never_run_on_the_turn_session(
    committed: tuple[Maker, str],
) -> None:
    maker, marker = committed
    await _seed(maker, marker)

    async with maker() as turn:
        service = await ToolDependencies(db_session=turn).get_connector_service()
        assert owns_session(service)
        async with connector_unit_of_work(service) as unit:
            assert unit.db is not turn
        assert not turn.in_transaction()
