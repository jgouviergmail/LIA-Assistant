"""Physical requests, redirects and retries all consume the same bounded read account."""

from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest

from src.core.read_budget import ReadCallBudget, ReadCallLimit, read_call_budget
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials, ConnectorCredentials

pytestmark = pytest.mark.unit
OWNER = UUID(int=1)


class KeyClient(BaseAPIKeyClient):
    connector_type = ConnectorType.OPENWEATHERMAP
    api_base_url = "https://fictional.example.test"


@pytest.mark.parametrize("family", ["oauth", "key"])
async def test_actual_client_request_hook_refuses_second_exchange_before_transport(
    family: str,
) -> None:
    client = (
        BaseOAuthClient(
            user_id=OWNER,
            credentials=ConnectorCredentials(access_token="fictional"),
            connector_service=MagicMock(),
        )
        if family == "oauth"
        else KeyClient(user_id=OWNER, credentials=APIKeyCredentials(api_key="fictional"))
    )
    http = await client._get_client()
    sent = []

    def receive(request):
        sent.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    hooks = http.event_hooks
    await http.aclose()
    http = httpx.AsyncClient(transport=httpx.MockTransport(receive), event_hooks=hooks)
    client._http_client = http
    budget = ReadCallBudget(owner=OWNER, limit=1)
    try:
        with read_call_budget(budget):
            await http.get("https://fictional.example.test/first")
            with pytest.raises(ReadCallLimit):
                await http.get("https://fictional.example.test/second")
        assert sent == ["/first"] and budget.calls == 1
    finally:
        await client.close()
