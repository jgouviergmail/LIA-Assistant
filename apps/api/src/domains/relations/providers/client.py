"""Building a provider client from outside the agent layer (Bloc C).

``connectors.provider_resolver.resolve_client_for_category`` needs
``ToolDependencies`` — an agents-layer concept a read-only CRM has no business
holding. The CRM's section fetchers open their provider through the shared
door, ``connectors.active_client`` (ADR-304): one short session of its own for
the provider, the credentials and the client, closed before the provider is
called — this module used to hold its own session open for the whole read —
and a transport closed on EVERY path, the body's failure included.

What this layer adds is the CRM's single sentence for every reason a provider
cannot be reached: it is not plugged in (``ProviderNotConfigured``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.domains.connectors.active_client import ActiveClient, open_active_client

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True)
class CategoryClient:
    """An open provider client, with the provider that answered.

    Attributes:
        client: The provider client, ready to call.
        connector_type: Which provider answered.
    """

    client: Any
    connector_type: Any


class ProviderNotConfigured(Exception):
    """No usable connector for this category.

    Covers "none active", "credentials gone" and "no client registered" — from
    the reader's side they are the same sentence: this provider is not plugged
    in. Distinguishing them would produce three messages for one action
    (go and connect it).
    """


@asynccontextmanager
async def open_category_client(
    functional_category: str, user_id: UUID
) -> AsyncIterator[CategoryClient]:
    """Yield the active client for a category, then close its transport.

    Args:
        functional_category: "contacts" | "email" | "calendar".
        user_id: Owner of the connector.

    Yields:
        The client and its connector type; no database session is open while
        the caller uses it.

    Raises:
        ProviderNotConfigured: When no usable connector exists.
    """
    async with open_active_client(functional_category, user_id) as opened:
        if not isinstance(opened, ActiveClient):
            raise ProviderNotConfigured(functional_category)
        yield CategoryClient(client=opened.client, connector_type=opened.connector_type)
