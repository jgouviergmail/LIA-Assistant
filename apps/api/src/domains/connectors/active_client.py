"""One door to the account's active client for a functional category (ADR-304).

Resolving the active provider, reading the right shape of credentials, finding
the client class and building the client was written out — eight lines each
time — in the briefing, the heartbeat, the moments, the telephony context and
the relations lens, every copy on its CALLER's session. A client can only
refresh a token on a session its caller keeps open, so every one of them held
a transaction for as long as the provider answered: measured in production on
2026-09-22 as ``idle in transaction`` sessions of 11 to 330 seconds.

``open_active_client`` reads everything a surface needs in ONE short session
of its own — the provider, the credentials, and, when asked, the owner's
configured default container (``owner_defaults``) — closes it, and only then
builds the client, on a ``DetachedConnectorService``: a token refresh opens its
own session for the length of the refresh. The caller holds nothing.

**Every refusal is NAMED** (``ClientUnavailable``), and the caller decides what
it means: « connect a calendar » and « your connection expired » are two
different things to tell someone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import (
    OwnerContainer,
    read_owner_container_name,
)
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService


class ClientUnavailable(str, Enum):
    """Why the category's client could not be opened."""

    NO_CONNECTOR = "no_connector"
    NO_CREDENTIALS = "no_credentials"
    NO_CLIENT = "no_client"


@dataclass(frozen=True, slots=True)
class ActiveClient:
    """An open provider client, and what was read with it.

    Attributes:
        client: The provider client, live for the length of the ``async with``.
        connector_type: Which provider answered.
        preferred_name: The owner's configured default container (a calendar,
            a task list) when one was asked for; resolve it on the network
            with ``owner_defaults.resolve_owner_container_id``.
    """

    client: Any
    connector_type: ConnectorType
    preferred_name: str | None


@dataclass(frozen=True, slots=True)
class _Opening:
    connector_type: ConnectorType
    credentials: Any
    preferred_name: str | None


@asynccontextmanager
async def open_active_client(
    category: str, user_id: UUID, *, container: OwnerContainer | None = None
) -> AsyncIterator[ActiveClient | ClientUnavailable]:
    """Open the account's active client for ``category``, and always close it.

    Args:
        category: ``calendar`` | ``email`` | ``contacts`` | ``tasks``.
        user_id: Whose provider.
        container: The owner's default container to read with it, if any.

    Yields:
        The open client, or the named reason it could not be opened. No
        database session is open while the caller uses it.
    """
    connectors = DetachedConnectorService()
    async with connectors.unit_of_work() as service:
        opening = await _read_opening(service, category, user_id, container)
    if isinstance(opening, ClientUnavailable):
        yield opening
        return
    client_class = ClientRegistry.get_client_class(opening.connector_type)
    if client_class is None:
        yield ClientUnavailable.NO_CLIENT
        return
    client = client_class(user_id, opening.credentials, connectors)
    try:
        yield ActiveClient(
            client=client,
            connector_type=opening.connector_type,
            preferred_name=opening.preferred_name,
        )
    finally:
        # Deterministic close on every path, the caller's failure included:
        # a per-instance transport left open is a leak under load.
        await client.close()


async def _read_opening(
    service: ConnectorService,
    category: str,
    user_id: UUID,
    container: OwnerContainer | None,
) -> _Opening | ClientUnavailable:
    """Everything the door reads, in the one session it holds."""
    connector_type = await resolve_active_connector(user_id, category, service)
    if connector_type is None:
        return ClientUnavailable.NO_CONNECTOR
    credentials: Any = (
        await service.get_apple_credentials(user_id, connector_type)
        if connector_type.is_apple
        else await service.get_connector_credentials(user_id, connector_type)
    )
    if not credentials:
        return ClientUnavailable.NO_CREDENTIALS
    preferred_name = (
        await read_owner_container_name(service.db, user_id, connector_type, container)
        if container is not None
        else None
    )
    return _Opening(connector_type, credentials, preferred_name)
