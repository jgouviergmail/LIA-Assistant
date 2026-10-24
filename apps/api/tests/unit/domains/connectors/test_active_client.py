"""One door to the account's active client for a category, holding no session (ADR-304).

The same eight lines — resolve the active provider, read the right shape of
credentials, find the client class, build the client — were copied into the
briefing, the heartbeat, the moments, the telephony context and the relations
lens, each on its CALLER's session, so every one held a transaction open for as
long as the provider answered. The door reads everything in one short session
of its own, closes it, and only then hands the client over.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.connectors import active_client
from src.domains.connectors.active_client import (
    ActiveClient,
    ClientUnavailable,
    open_active_client,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.oauth_refresh import Refreshed, StoredToken
from src.domains.connectors.oauth_refresh_targets import StoredCredentials
from src.domains.connectors.preferences.owner_defaults import CALENDAR
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


class _Units:
    """A detached connector service whose units count the sessions open."""

    open = 0

    def __init__(self, service: MagicMock) -> None:
        self.service = service

    @contextlib.asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[MagicMock]:
        _Units.open += 1
        try:
            yield self.service
        finally:
            _Units.open -= 1


def _type(*, apple: bool = False) -> MagicMock:
    connector_type = MagicMock()
    connector_type.is_apple = apple
    return connector_type


_TOKEN = ConnectorCredentials(access_token="creds")


class _ValidToken:
    """A holder whose token is valid: the door's fast path only asks whether it expires.

    Each ask notes how many sessions of ours were open at that moment.
    """

    kind = "connector"
    flight_key = "connector:active-client-test"
    user_id = USER

    def __init__(self) -> None:
        self.sessions_open_when_asked: list[int] = []

    def needs_refresh(self, credentials: ConnectorCredentials, refresh_before: Any) -> bool:
        self.sessions_open_when_asked.append(_Units.open)
        return False

    async def read(self, db: Any) -> StoredToken[ConnectorCredentials] | None:
        raise AssertionError("a valid token the caller holds costs no read")

    async def exchange(self, credentials: ConnectorCredentials) -> Refreshed[ConnectorCredentials]:
        raise AssertionError("a valid token is never exchanged")

    async def write_if_unchanged(self, db: Any, expected: str, refreshed: Any) -> bool:
        raise AssertionError("a valid token is never written")

    async def revoke_if_unchanged(self, db: Any, expected: str) -> bool:
        raise AssertionError("a valid token is never revoked")

    def inactive_error(self) -> Exception:
        return AssertionError("inactive")

    def revoked_error(self, status_code: int | None) -> Exception:
        return AssertionError("revoked")

    def failed_error(self) -> Exception:
        return AssertionError("failed")


def _stored(credentials: ConnectorCredentials = _TOKEN) -> StoredCredentials:
    return StoredCredentials(
        _ValidToken(),
        StoredToken("ciphertext", credentials, True),
        USER,
        ConnectorType.GOOGLE_CALENDAR,
    )


def _service(credentials: Any = _TOKEN) -> MagicMock:
    service = MagicMock()
    service.db = MagicMock()
    service.read_connector_credentials = AsyncMock(
        return_value=None if credentials is None else _stored(credentials)
    )
    service.get_apple_credentials = AsyncMock(return_value=credentials)
    return service


@contextlib.contextmanager
def _patched(
    *,
    resolved: Any,
    service: MagicMock,
    client_class: Any = None,
    preferred: str | None = None,
) -> Any:
    units = _Units(service)
    client = MagicMock()
    client.close = AsyncMock()
    cls = client_class if client_class is not None else MagicMock(return_value=client)
    with (
        patch.object(active_client, "DetachedConnectorService", return_value=units),
        patch.object(active_client, "resolve_active_connector", AsyncMock(return_value=resolved)),
        patch.object(active_client.ClientRegistry, "get_client_class", return_value=cls),
        patch.object(
            active_client, "read_owner_container_name", AsyncMock(return_value=preferred)
        ) as read_name,
    ):
        yield units, cls, client, read_name


async def test_no_active_connector_is_named_and_builds_nothing() -> None:
    with _patched(resolved=None, service=_service()) as (_units, cls, _client, _read):
        async with open_active_client("calendar", USER) as opened:
            assert opened is ClientUnavailable.NO_CONNECTOR
    cls.assert_not_called()


async def test_missing_credentials_are_named() -> None:
    with _patched(resolved=_type(), service=_service(credentials=None)) as (_u, cls, _c, _r):
        async with open_active_client("email", USER) as opened:
            assert opened is ClientUnavailable.NO_CREDENTIALS
    cls.assert_not_called()


async def test_an_unregistered_client_is_named() -> None:
    with (
        _patched(resolved=_type(), service=_service()) as (_u, _cls, _c, _r),
        patch.object(active_client.ClientRegistry, "get_client_class", return_value=None),
    ):
        async with open_active_client("tasks", USER) as opened:
            assert opened is ClientUnavailable.NO_CLIENT


async def test_the_session_is_closed_before_the_caller_touches_the_client() -> None:
    service = _service()
    with _patched(resolved=_type(), service=service) as (units, cls, client, _read):
        async with open_active_client("email", USER) as opened:
            assert isinstance(opened, ActiveClient)
            assert _Units.open == 0, "a session was still open while the provider is called"
            assert opened.client is client
        # The client writes through the detached service, never a caller session.
        assert cls.call_args.args == (USER, _TOKEN, units)
    client.close.assert_awaited_once()


async def test_the_token_is_freshened_once_the_reading_session_is_closed() -> None:
    """A refresh is a network call: the door is asked with no session of ours open."""
    fresh = ConnectorCredentials(access_token="fresh-access")
    service = _service(credentials=fresh)
    holder = service.read_connector_credentials.return_value.target
    with _patched(resolved=_type(), service=service) as (units, cls, _client, _read):
        async with open_active_client("calendar", USER) as opened:
            assert isinstance(opened, ActiveClient)
    assert holder.sessions_open_when_asked == [0]
    assert cls.call_args.args == (USER, fresh, units)


async def test_the_client_is_closed_even_when_the_callers_body_raises() -> None:
    with _patched(resolved=_type(), service=_service()) as (_u, _cls, client, _r):
        with pytest.raises(RuntimeError):
            async with open_active_client("email", USER):
                raise RuntimeError("the caller's own failure")
    client.close.assert_awaited_once()


async def test_an_apple_provider_reads_its_own_credentials_shape() -> None:
    service = _service()
    with _patched(resolved=_type(apple=True), service=service):
        async with open_active_client("calendar", USER) as opened:
            assert isinstance(opened, ActiveClient)
    service.get_apple_credentials.assert_awaited_once()
    service.read_connector_credentials.assert_not_awaited()


async def test_the_owners_default_is_read_in_the_same_short_session() -> None:
    resolved = _type()
    service = _service()
    with _patched(resolved=resolved, service=service, preferred="Work") as (_u, _c, _cl, read):
        async with open_active_client("calendar", USER, container=CALENDAR) as opened:
            assert isinstance(opened, ActiveClient)
            assert opened.preferred_name == "Work"
    read.assert_awaited_once_with(service.db, USER, resolved, CALENDAR)


async def test_no_container_asked_reads_no_preference() -> None:
    with _patched(resolved=_type(), service=_service()) as (_u, _c, _cl, read):
        async with open_active_client("email", USER) as opened:
            assert isinstance(opened, ActiveClient)
            assert opened.preferred_name is None
    read.assert_not_awaited()


def test_every_registered_client_can_be_closed() -> None:
    """The door closes every client it builds, unconditionally.

    A client with no ``close`` would be an AttributeError in a ``finally`` —
    the worst place for one — so the contract is held here rather than
    tolerated there: every class the registry can hand out owns an async
    ``close`` (inherited from its base: OAuth, Apple).
    """
    import inspect

    from src.domains.connectors.clients.registry import ClientRegistry

    ClientRegistry._ensure_initialized()
    assert ClientRegistry._registry, "the registry is empty: the guard would pass vacuously"
    missing = {
        connector_type.value: cls.__name__
        for connector_type, cls in ClientRegistry._registry.items()
        if not inspect.iscoroutinefunction(getattr(cls, "close", None))
    }
    assert not missing, f"registered clients the door cannot close: {missing}"
