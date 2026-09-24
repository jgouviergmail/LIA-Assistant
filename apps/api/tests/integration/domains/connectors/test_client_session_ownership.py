"""A connector client never closes, nor keeps open, the transaction of its caller (ADR-304).

Proved on a real PostgreSQL session, because the defect is a property of
SQLAlchemy's session lifecycle that no mock reproduces: the client entered its
caller's session as a context manager (``async with self.connector_service.db``),
and ``AsyncSession.__aexit__`` CLOSES it — expunging every object the caller had
loaded. A caller that then wrote to one of them (the Drive push path writing
the channel's page token) committed nothing, in silence.

A ``DetachedConnectorService`` is the other half: a caller that holds no
session hands the client one, and the client's own writes run on a session of
its own, committed and released at the end of the unit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import Connector, ConnectorStatus
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.users.models import User
from tests.fixtures.factories import ConnectorFactory, UserFactory

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def account(async_session: AsyncSession) -> tuple[User, Connector]:
    user = UserFactory.create(email="session-owner@example.test", full_name="Session Owner")
    async_session.add(user)
    await async_session.commit()
    connector = ConnectorFactory.create_gmail_connector(
        user_id=str(user.id), email="session-owner@example.test", status=ConnectorStatus.ACTIVE
    )
    async_session.add(connector)
    await async_session.commit()
    return user, connector


@asynccontextmanager
async def _no_lock(*_args: Any, **_kwargs: Any) -> AsyncIterator[None]:
    yield None


def _expired() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="old",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )


async def _connector_status(session: AsyncSession, connector_id: Any) -> ConnectorStatus:
    return (
        await session.execute(select(Connector.status).where(Connector.id == connector_id))
    ).scalar_one()


async def test_an_invalidation_leaves_the_callers_objects_attached(
    async_session: AsyncSession, account: tuple[User, Connector]
) -> None:
    user, connector = account
    client = GoogleGmailClient(user.id, _expired(), ConnectorService(async_session))

    with patch.object(ConnectorService, "_invalidate_user_connectors_cache", AsyncMock()):
        await client._invalidate_connector_on_auth_failure("401 from the provider")

    assert user in async_session, "the client closed its caller's session and expunged its rows"
    assert await _connector_status(async_session, connector.id) == ConnectorStatus.ERROR


async def test_a_token_refresh_leaves_the_callers_objects_attached(
    async_session: AsyncSession, account: tuple[User, Connector]
) -> None:
    user, _connector = account
    client = GoogleGmailClient(user.id, _expired(), ConnectorService(async_session))
    fresh = ConnectorCredentials(
        access_token="new",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    with (
        patch("src.domains.connectors.clients.base_oauth_client.get_redis_session", AsyncMock()),
        patch("src.domains.connectors.clients.base_oauth_client.OAuthLock", _no_lock),
        patch.object(
            ConnectorService, "get_connector_credentials", AsyncMock(return_value=_expired())
        ),
        patch.object(ConnectorService, "_refresh_oauth_token", AsyncMock(return_value=fresh)),
    ):
        token = await client._ensure_valid_token()

    assert token == "new"
    assert user in async_session, "the client closed its caller's session and expunged its rows"


async def test_a_detached_refresh_calls_the_provider_with_no_transaction_open(
    async_session: AsyncSession, account: tuple[User, Connector]
) -> None:
    """The token endpoint is a network call: a session the unit OWNS ends its reads first."""
    user, _connector = account
    client = GoogleGmailClient(user.id, _expired(), DetachedConnectorService())
    seen: list[bool] = []

    async def _refresh(service: ConnectorService, *_args: Any) -> ConnectorCredentials:
        seen.append(service.db.in_transaction())
        return ConnectorCredentials(
            access_token="new", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )

    @asynccontextmanager
    async def _own_session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with (
        patch("src.domains.connectors.clients.base_oauth_client.get_redis_session", AsyncMock()),
        patch("src.domains.connectors.clients.base_oauth_client.OAuthLock", _no_lock),
        patch("src.domains.connectors.session_scope.get_db_context", _own_session),
        patch.object(
            ConnectorService, "get_connector_credentials", AsyncMock(return_value=_expired())
        ),
        patch.object(ConnectorService, "_refresh_oauth_token", _refresh),
    ):
        await client._ensure_valid_token()

    assert seen == [False]


async def test_a_failed_refresh_never_commits_the_callers_pending_writes(
    async_session: AsyncSession, account: tuple[User, Connector]
) -> None:
    """A caller's transaction is the caller's: the refresh never ends it early."""
    user, _connector = account
    user_id = user.id
    user.full_name = "Pending, never committed"
    client = GoogleGmailClient(user_id, _expired(), ConnectorService(async_session))

    with (
        patch("src.domains.connectors.clients.base_oauth_client.get_redis_session", AsyncMock()),
        patch("src.domains.connectors.clients.base_oauth_client.OAuthLock", _no_lock),
        patch.object(
            ConnectorService, "get_connector_credentials", AsyncMock(return_value=_expired())
        ),
        patch.object(
            ConnectorService,
            "_refresh_oauth_token",
            AsyncMock(side_effect=RuntimeError("provider down")),
        ),
        pytest.raises(RuntimeError),
    ):
        await client._ensure_valid_token()

    await async_session.rollback()
    stored = (
        await async_session.execute(select(User.full_name).where(User.id == user_id))
    ).scalar_one()
    assert stored == "Session Owner"


async def test_a_detached_client_writes_on_a_session_of_its_own(
    async_session: AsyncSession, account: tuple[User, Connector]
) -> None:
    user, connector = account
    opened: list[AsyncSession] = []

    @asynccontextmanager
    async def _own_session() -> AsyncIterator[AsyncSession]:
        opened.append(async_session)
        yield async_session
        await async_session.commit()

    client = GoogleGmailClient(user.id, _expired(), DetachedConnectorService())
    with (
        patch("src.domains.connectors.session_scope.get_db_context", _own_session),
        patch.object(ConnectorService, "_invalidate_user_connectors_cache", AsyncMock()),
    ):
        await client._invalidate_connector_on_auth_failure("401 from the provider")

    assert len(opened) == 1, "the detached service opens exactly one session for the unit"
    assert await _connector_status(async_session, connector.id) == ConnectorStatus.ERROR
