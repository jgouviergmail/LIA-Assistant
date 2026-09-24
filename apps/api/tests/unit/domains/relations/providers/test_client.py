"""The CRM's provider opening — one sentence for every unusable provider.

The opening itself (provider, credentials shape, client class, the transport
closed on every path, no session held) is the shared door's, tested in
``tests/unit/domains/connectors/test_active_client.py`` (ADR-304). What this
layer owns is the CRM's reading of a refusal: an unusable connector raises
``ProviderNotConfigured`` for EVERY reason it can be unusable — a missed branch
would hand a fetcher half a client and fail deep inside it, where the caller
can no longer tell "not plugged in" from "the read failed".
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.relations.providers import client as category_client
from src.domains.relations.providers.client import ProviderNotConfigured, open_category_client

pytestmark = pytest.mark.unit

USER_ID = uuid4()


def _door(opened: Any) -> Any:
    @contextlib.asynccontextmanager
    async def _open(category: str, user_id: Any) -> AsyncIterator[Any]:
        yield opened

    return _open


@pytest.mark.parametrize("reason", list(ClientUnavailable))
async def test_every_unusable_provider_is_not_plugged_in(reason: ClientUnavailable) -> None:
    with (
        patch.object(category_client, "open_active_client", _door(reason)),
        pytest.raises(ProviderNotConfigured),
    ):
        async with open_category_client("contacts", USER_ID):
            pass


async def test_it_yields_the_client_and_the_provider_that_answered() -> None:
    client, connector_type = MagicMock(), MagicMock()
    opened = ActiveClient(client=client, connector_type=connector_type, preferred_name=None)
    with patch.object(category_client, "open_active_client", _door(opened)):
        async with open_category_client("email", USER_ID) as category:
            assert category.client is client
            assert category.connector_type is connector_type
            assert not hasattr(category, "session"), "no session travels with the client"
