"""The hosts a run may carry a credential for, derived from the client classes.

Each API-key client already declares where its service lives and how the
key travels (``api_base_url``, ``auth_method``, ``auth_header_name``,
``auth_query_param``, ``auth_header_prefix``). Reading those is what keeps
the proxy's rule and the client's real call identical: a table typed by hand
would name a header the client stopped sending (ADR-185's doctrine, pointed
at credentials).

The list of classes is explicit and guarded: ``__subclasses__`` depends on
what happens to be imported, and a class missed here would leave a person
asked for a host their own connector already permits.
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from src.domains.agents.python_sandbox.egress.hosts import ConnectorHost
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

#: Every ``BaseAPIKeyClient`` subclass of the connectors package — a test
#: walks the package's AST and refuses an omission.
API_KEY_CLIENTS: tuple[type[BaseAPIKeyClient], ...] = (
    BraveSearchClient,
    PerplexityClient,
    OpenWeatherMapClient,
)


class ConnectorGate(Protocol):
    """What the tool's dependency container already offers (thread-safe)."""

    async def is_connector_active(self, user_id: UUID, connector_type: ConnectorType) -> bool: ...

    async def get_api_key_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> APIKeyCredentials | None: ...


def derive_connector_hosts() -> dict[str, ConnectorHost]:
    """``{host: ConnectorHost}`` for every API-key client class."""
    hosts: dict[str, ConnectorHost] = {}
    for client in API_KEY_CLIENTS:
        host = urlsplit(client.api_base_url).hostname
        if not host:
            raise RuntimeError(f"{client.__name__}.api_base_url has no host")
        by_header = client.auth_method == "header"
        hosts[host.lower()] = ConnectorHost(
            host=host.lower(),
            connector=client.connector_type.value,
            auth_method="header" if by_header else "query",
            auth_name=client.auth_header_name if by_header else client.auth_query_param,
            auth_prefix=client.auth_header_prefix if by_header else "",
        )
    return hosts


async def active_connector_hosts(gate: ConnectorGate, user_id: UUID) -> dict[str, ConnectorHost]:
    """The derived hosts whose connector is ACTIVE for this account.

    Three indexed lookups through the tool's own connector service; an
    inactive, revoked or errored connector brings no credential and its host
    falls through to the other statuses.
    """
    active: dict[str, ConnectorHost] = {}
    for host, spec in derive_connector_hosts().items():
        if await gate.is_connector_active(user_id, ConnectorType(spec.connector)):
            active[host] = spec
    return active


async def real_keys_for(
    gate: ConnectorGate, user_id: UUID, hosts: tuple[ConnectorHost, ...]
) -> dict[str, str]:
    """``{connector: api_key}`` for the connector hosts a run declared.

    A connector that turns out to hold no key (deactivated between the
    listing and now) is simply absent — the run then reaches that host
    without a credential rather than failing on a race.
    """
    keys: dict[str, str] = {}
    for spec in hosts:
        credentials = await gate.get_api_key_credentials(user_id, ConnectorType(spec.connector))
        if credentials is not None and credentials.api_key:
            keys[spec.connector] = credentials.api_key
    return keys


__all__ = [
    "API_KEY_CLIENTS",
    "ConnectorGate",
    "active_connector_hosts",
    "derive_connector_hosts",
    "real_keys_for",
]
