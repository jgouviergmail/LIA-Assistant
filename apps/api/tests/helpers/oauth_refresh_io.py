"""The refresh door's I/O, scripted, so its callers are tested through the REAL door.

A caller of the one refresh door (audit AC-029) — the connector service, a client, the
proactive job — is judged on what the door decides for it: no exchange for a token valid
past the margin, one exchange for an expiring one. Only the door's edges are scripted:
its short sessions (one connector row, every conditional write landing), its Redis (in
memory), and the provider exchange. The rules in between are the production ones.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql import ClauseElement

from src.core.security import encrypt_data
from src.domains.connectors import oauth_refresh, oauth_refresh_targets
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshedToken,
    RefreshRefused,
    TokenEndpoint,
)
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.utils import shared_flight
from tests.helpers.redis_double import InMemoryRedis


@dataclass
class ServedCredentials:
    """What a service's read hands its caller, freshening to fixed credentials.

    Attributes:
        credentials: What ``fresh()`` serves.
        asked: How many times the caller asked for them.
    """

    credentials: ConnectorCredentials
    asked: int = 0

    async def fresh(self) -> ConnectorCredentials:
        """The fixed credentials, as the refresh door would serve them."""
        self.asked += 1
        return self.credentials


def fresh_token(access_token: str = "fresh-access") -> RefreshedToken:
    """A provider answer valid for an hour, keeping the refresh token sent."""
    return RefreshedToken(
        access_token=access_token,
        refresh_token="refresh-after",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        reported_scopes=frozenset(),
    )


@dataclass
class ScriptedDoor:
    """What the door's edges answer, and what crossed them.

    Attributes:
        answer: The provider's answer to every exchange.
        exchanged: The refresh token of every exchange, in order.
        redis: The in-memory Redis of the claim and the verdict markers.
        session: The short session every read and write of the door runs on.
    """

    answer: RefreshedToken | RefreshRefused
    exchanged: list[str] = field(default_factory=list)
    redis: InMemoryRedis = field(default_factory=InMemoryRedis)
    session: AsyncMock = field(default_factory=lambda: AsyncMock(spec=AsyncSession))


def install_scripted_door(
    monkeypatch: pytest.MonkeyPatch,
    connector: Connector,
    *,
    answer: RefreshedToken | RefreshRefused | None = None,
) -> ScriptedDoor:
    """Script the door's edges around one connector row.

    Args:
        monkeypatch: The test's monkeypatch.
        connector: The row every read of the door returns.
        answer: The provider's answer; a fresh token by default.

    Returns:
        The scripted edges, for the test's assertions.
    """
    door = ScriptedDoor(answer=answer if answer is not None else fresh_token())
    door.session.scalar = AsyncMock(return_value=connector)

    async def apply(statement: ClauseElement, *_args: object, **_kwargs: object) -> object:
        """Apply an UPDATE's SET values to the one row (its WHERE is proven on PostgreSQL)."""
        values = statement.compile().params
        if "credentials_encrypted" in values:
            connector.credentials_encrypted = values["credentials_encrypted"]
        if "status" in values:
            connector.status = values["status"]
        return SimpleNamespace(rowcount=1)

    door.session.execute = AsyncMock(side_effect=apply)

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield door.session

    async def cache() -> InMemoryRedis:
        return door.redis

    async def exchange(
        endpoint: TokenEndpoint,
        *,
        refresh_token: str,
        scopes: list[str],
        owner_id: UUID | None,
    ) -> RefreshedToken:
        door.exchanged.append(refresh_token)
        if isinstance(door.answer, RefreshRefused):
            raise door.answer
        return door.answer

    monkeypatch.setattr(oauth_refresh, "get_db_context", sessions)
    monkeypatch.setattr(oauth_refresh, "get_redis_cache", cache)
    monkeypatch.setattr(shared_flight, "get_redis_cache", cache)
    monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", exchange)
    return door


def expired_ciphertext(refresh_token: str = "refresh-1") -> str:
    """Stored credentials whose access token expired five minutes ago."""
    return encrypt_data(
        ConnectorCredentials(
            access_token="stale",
            refresh_token=refresh_token,
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        ).model_dump_json()
    )


async def commit_expired_connector(
    engine: AsyncEngine,
    owner: UUID,
    *,
    connector_type: ConnectorType = ConnectorType.GOOGLE_GMAIL,
    status: ConnectorStatus = ConnectorStatus.ACTIVE,
    scopes: list[str] | None = None,
) -> Connector:
    """A connector committed outside every test transaction, its token expired.

    The refresh door reads and writes on sessions of its own: a row the test's
    rollback transaction holds is invisible to it.

    Args:
        engine: The test engine.
        owner: A committed account (``commit_owner``).
        connector_type: The connector's type.
        status: The connector's status.
        scopes: Its granted scopes; none by default.

    Returns:
        The committed row, detached with every attribute loaded.
    """
    async with AsyncSession(engine, expire_on_commit=False) as db:
        connector = Connector(
            user_id=owner,
            connector_type=connector_type,
            status=status,
            scopes=list(scopes or []),
            credentials_encrypted=expired_ciphertext(),
        )
        db.add(connector)
        await db.commit()
        return connector
