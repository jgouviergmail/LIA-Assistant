"""Both native HTTP seams refuse an account mismatch, including token refresh."""

from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest

from src.core.card_composition import (
    CardComposition,
    CardCompositionUnavailable,
    card_composition_ctx,
)
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["_make_request", "_make_authenticated_request"])
@pytest.mark.parametrize("when", ["initial", "during_refresh"])
async def test_actual_http_request_never_reaches_a_replaced_account(method, when):
    user = UUID(int=1)
    grant = str(UUID(int=4))
    credentials = ConnectorCredentials(
        access_token="secret",
        account_binding=grant if when == "during_refresh" else str(UUID(int=5)),
    )
    client = GoogleGmailClient(user, credentials, Mock())
    http = AsyncMock()
    http.get.return_value = httpx.Response(200, json={"id": "sent"})
    client._get_http_client = AsyncMock(return_value=http)
    client._get_client = AsyncMock(return_value=http)
    client._rate_limit = AsyncMock()
    client._apply_rate_limit = AsyncMock()
    client._is_circuit_breaker_enabled = Mock(return_value=False)

    async def refresh():
        client.credentials = client.credentials.model_copy(
            update={"account_binding": str(UUID(int=5))}
        )
        return "replacement-token"

    client._ensure_valid_token = AsyncMock(side_effect=refresh)
    token = card_composition_ctx.set(
        CardComposition(user, "EMAIL", "target", "reply", "google_gmail", grant)
    )
    try:
        with pytest.raises(CardCompositionUnavailable):
            await getattr(client, method)(
                "GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages/target"
            )
        http.get.assert_not_awaited()
        if when == "initial":
            client._ensure_valid_token.assert_not_awaited()
    finally:
        card_composition_ctx.reset(token)
