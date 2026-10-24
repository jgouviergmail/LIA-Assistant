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

A token refresh goes through the one refresh door (audit AC-029), which reads and
writes on sessions of its OWN: the refresh tests therefore use rows committed
outside the test's rollback transaction, so that the door's sessions see them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ValidationError
from src.domains.connectors import oauth_refresh_targets, session_scope
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import Connector, ConnectorStatus
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshedToken,
    RefreshRefusal,
    RefreshRefused,
)
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from tests.fixtures.factories import ConnectorFactory, UserFactory
from tests.helpers.committed_users import commit_owner
from tests.helpers.oauth_refresh_io import commit_expired_connector

pytestmark = pytest.mark.integration

_GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"


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


@pytest_asyncio.fixture
async def committed_owner(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> UUID:
    """An account the refresh door's own sessions can see, removed after the test."""
    return await commit_owner(async_engine, committed_user_ids, full_name="Session Owner")


def _expired() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="old",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )


def _issuing(access: str, observe: Callable[[], None]) -> Callable[..., Awaitable[RefreshedToken]]:
    async def provider(*_args: object, **_kwargs: object) -> RefreshedToken:
        observe()
        return RefreshedToken(
            access_token=access,
            refresh_token="refresh-2",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            reported_scopes=frozenset(),
        )

    return provider


async def _outage(*_args: object, **_kwargs: object) -> RefreshedToken:
    raise RefreshRefused(RefreshRefusal.TRANSIENT, status_code=503)


async def _connector_status(session: AsyncSession, connector_id: UUID) -> ConnectorStatus:
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
    """Another process already refreshed the stored token: the client's refresh serves
    it, and its caller's session — borrowed, never entered — keeps every row it holds."""
    user, _connector = account
    client = GoogleGmailClient(user.id, _expired(), ConnectorService(async_session))

    token = await client._ensure_valid_token()

    assert token == "test-access-token"
    assert user in async_session, "the client closed its caller's session and expunged its rows"


async def test_a_detached_refresh_calls_the_provider_with_no_transaction_open(
    async_engine: AsyncEngine, committed_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token endpoint is a network call: the unit the client owns is over by then."""
    await commit_expired_connector(async_engine, committed_owner, scopes=[_GMAIL_READ])
    units: list[AsyncSession] = []
    real_session = get_db_context

    @asynccontextmanager
    async def recorded() -> AsyncIterator[AsyncSession]:
        async with real_session() as db:
            units.append(db)
            yield db

    in_transaction_at_exchange: list[list[bool]] = []

    def observe() -> None:
        in_transaction_at_exchange.append([db.in_transaction() for db in units])

    monkeypatch.setattr(session_scope, "get_db_context", recorded)
    monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", _issuing("new", observe))
    client = GoogleGmailClient(committed_owner, _expired(), DetachedConnectorService())

    token = await client._ensure_valid_token()

    assert token == "new"
    assert len(units) == 1, "the detached service opens exactly one session for the read"
    assert in_transaction_at_exchange == [[False]], "a unit's transaction waited on the provider"


async def test_a_failed_refresh_never_commits_the_callers_pending_writes(
    async_engine: AsyncEngine, committed_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller's transaction is the caller's: the refresh never ends it, even failing."""
    await commit_expired_connector(async_engine, committed_owner, scopes=[_GMAIL_READ])
    monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", _outage)

    async with AsyncSession(async_engine, expire_on_commit=False) as caller:
        user = await caller.get(User, committed_owner)
        assert user is not None
        user.full_name = "Pending, never committed"
        client = GoogleGmailClient(committed_owner, _expired(), ConnectorService(caller))

        with pytest.raises(ValidationError):
            await client._ensure_valid_token()

        await caller.rollback()

    async with AsyncSession(async_engine) as reader:
        stored = (
            await reader.execute(select(User.full_name).where(User.id == committed_owner))
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
