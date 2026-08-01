"""Building a provider client from outside the agent layer (Bloc C).

``connectors.provider_resolver.resolve_client_for_category`` needs
``ToolDependencies`` — an agents-layer concept a read-only CRM has no business
holding. The established precedent for a non-agent consumer is
``connectors/birthdays.py`` (and ``briefing/fetchers.py``): resolve the active
connector, read its credentials, instantiate the registered client, and close
the transport deterministically. This module is that precedent, made
provider-agnostic and reusable by the three section fetchers.

Every client is used inside ``open_category_client`` so its per-instance httpx
transport is closed on EVERY path — the same doctrine as the briefing weather
fetcher, and the reason none of these fetchers leaks a connection on failure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.service import ConnectorService
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CategoryClient:
    """An open provider client, with what a fetcher needs to use it well.

    ``session`` and ``connector_type`` travel with the client because reading
    an OWNER's configured default container (their calendar, their task list)
    requires both — and reading the wrong container is the costliest shape of
    wrong answer this codebase has recorded (``connectors/preferences``).

    Attributes:
        client: The provider client, ready to call.
        connector_type: Which provider answered.
        session: The session the client's credentials live on — valid only
            inside the ``open_category_client`` block.
    """

    client: Any
    connector_type: Any
    session: Any


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

    Opens its OWN database session (fetcher context — briefing doctrine): the
    CRM request's session must never be shared with a concurrent fetcher, and
    a provider hiccup must not poison the transaction the rest of the page
    runs on.

    Args:
        functional_category: "contacts" | "email" | "calendar".
        user_id: Owner of the connector.

    Yields:
        The client, its connector type and the session they live on.

    Raises:
        ProviderNotConfigured: When no usable connector exists.
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(
            user_id, functional_category, connector_service
        )
        if resolved_type is None:
            raise ProviderNotConfigured(functional_category)

        credentials = (
            await connector_service.get_apple_credentials(user_id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user_id, resolved_type)
        )
        if not credentials:
            raise ProviderNotConfigured(functional_category)

        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            raise ProviderNotConfigured(functional_category)

        client = client_class(user_id, credentials, connector_service)
        try:
            yield CategoryClient(client=client, connector_type=resolved_type, session=db)
        finally:
            # Deterministic close on every path — a per-instance transport left
            # open is a resource warning at teardown and a leak under load.
            close = getattr(client, "close", None)
            if close is not None:
                await close()
