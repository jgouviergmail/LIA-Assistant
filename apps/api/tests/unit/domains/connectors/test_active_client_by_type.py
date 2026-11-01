"""The door for a service that belongs to no category — Drive and the Hue bridge (ADR-304).

The workbench opens the person's Drive and their Hue bridge by hand. Neither is
in a functional category, so the category door cannot resolve them, and the
eight lines it replaced must not come back either: ``open_client_by_type`` reads
the ONE connector row in a short session of its own, closes it, freshens an OAuth
token only then, and closes the client on every path.
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
    open_client_by_type,
)
from src.domains.connectors.errors import ConnectorRevokedError
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.oauth_refresh import StoredToken
from src.domains.connectors.oauth_refresh_targets import StoredCredentials
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

USER = uuid.uuid4()
_TOKEN = ConnectorCredentials(access_token="drive-token")


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


class _Holder:
    """A token holder that notes how many sessions were open when asked to freshen."""

    kind = "connector"
    flight_key = "connector:by-type-test"
    user_id = USER

    def __init__(self) -> None:
        self.sessions_open_when_asked: list[int] = []

    def needs_refresh(self, credentials: Any, refresh_before: Any) -> bool:
        self.sessions_open_when_asked.append(_Units.open)
        return False


def _stored() -> StoredCredentials:
    return StoredCredentials(
        _Holder(), StoredToken("ciphertext", _TOKEN, True), USER, ConnectorType.GOOGLE_DRIVE
    )


def _service(*, oauth: Any = None, hue: Any = None, revoked: bool = False) -> MagicMock:
    service = MagicMock()
    service.read_connector_credentials = AsyncMock(
        side_effect=ConnectorRevokedError(ConnectorType.GOOGLE_DRIVE, USER) if revoked else None,
        return_value=oauth,
    )
    service.get_hue_credentials = AsyncMock(return_value=hue)
    service.get_apple_credentials = AsyncMock(return_value=None)
    return service


@contextlib.contextmanager
def _patched(service: MagicMock, client_class: Any = None) -> Any:
    units = _Units(service)
    client = MagicMock()
    client.close = AsyncMock()
    cls = client_class if client_class is not None else MagicMock(return_value=client)
    with (
        patch.object(active_client, "DetachedConnectorService", return_value=units),
        patch.object(active_client.ClientRegistry, "get_client_class", return_value=cls),
    ):
        yield units, cls, client


async def test_an_absent_connector_is_named_and_builds_nothing() -> None:
    with _patched(_service()) as (_units, cls, _client):
        async with open_client_by_type(ConnectorType.GOOGLE_DRIVE, USER) as opened:
            assert opened is ClientUnavailable.NO_CONNECTOR
    cls.assert_not_called()


async def test_a_revoked_connector_is_absent_not_an_error() -> None:
    """A deliberate disconnection reads as « not connected », never as a 500."""
    with _patched(_service(revoked=True)) as (_units, cls, _client):
        async with open_client_by_type(ConnectorType.GOOGLE_DRIVE, USER) as opened:
            assert opened is ClientUnavailable.NO_CONNECTOR
    cls.assert_not_called()


async def test_drive_is_opened_with_no_session_held_and_a_token_freshened_after() -> None:
    stored = _stored()
    with _patched(_service(oauth=stored)) as (units, cls, client):
        async with open_client_by_type(ConnectorType.GOOGLE_DRIVE, USER) as opened:
            assert isinstance(opened, ActiveClient)
            assert _Units.open == 0, "a session was still open while the provider is called"
            assert opened.client is client
            assert opened.connector_type is ConnectorType.GOOGLE_DRIVE
    assert stored.target.sessions_open_when_asked == [0]
    assert cls.call_args.args == (USER, _TOKEN, units)
    client.close.assert_awaited_once()


async def test_the_hue_bridge_reads_its_own_credentials_shape() -> None:
    hue_credentials = MagicMock(name="HueBridgeCredentials")
    service = _service(hue=hue_credentials)
    with _patched(service) as (units, cls, _client):
        async with open_client_by_type(ConnectorType.PHILIPS_HUE, USER) as opened:
            assert isinstance(opened, ActiveClient)
    service.read_connector_credentials.assert_not_awaited()
    assert cls.call_args.args == (USER, hue_credentials, units)


async def test_an_unregistered_client_is_named() -> None:
    with (
        _patched(_service(oauth=_stored())) as (_units, _cls, _client),
        patch.object(active_client.ClientRegistry, "get_client_class", return_value=None),
    ):
        async with open_client_by_type(ConnectorType.GOOGLE_DRIVE, USER) as opened:
            assert opened is ClientUnavailable.NO_CLIENT


async def test_the_client_is_closed_even_when_the_callers_body_raises() -> None:
    with _patched(_service(oauth=_stored())) as (_units, _cls, client):
        with pytest.raises(RuntimeError):
            async with open_client_by_type(ConnectorType.GOOGLE_DRIVE, USER):
                raise RuntimeError("the caller's own failure")
    client.close.assert_awaited_once()
