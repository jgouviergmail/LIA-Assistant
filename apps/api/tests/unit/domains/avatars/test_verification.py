"""The activation probe is authenticated, bounded, and never opens a session."""

import httpx
import pytest

from src.domains.connectors.api_key_verifiers import API_KEY_FUNCTIONAL_VERIFIERS
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload,valid",
    [
        (200, [{"urls": "stun:stun.example.test"}], True),
        (401, {}, False),
        (200, {"session_token": "wrong-shape"}, False),
        (200, [{"urls": "https://untrusted.example.test"}], False),
    ],
)
async def test_activation_probe_only_reads_ice(monkeypatch, status, payload, valid):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json=payload)

    constructor = httpx.AsyncClient
    clients = []

    def make_client(**kwargs):
        client = constructor(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    verifier = API_KEY_FUNCTIONAL_VERIFIERS.get(ConnectorType.SIMLI)
    assert verifier is not None, "Simli must validate a key without billed creation"
    accepted, _ = await verifier("test-only-credential", None)
    assert accepted is valid
    assert [(r.method, r.url.path) for r in requests] == [("GET", "/compose/ice")]
    assert requests[0].headers["x-simli-api-key"] == "test-only-credential"
    assert clients[0].is_closed
