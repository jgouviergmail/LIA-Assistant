"""Provider requests are single-attempt, fixed-origin and bounded."""

import json
from uuid import UUID

import httpx
import pytest

from src.core.config import settings
from src.domains.avatars.client import SimliClient, SimliError

pytestmark = pytest.mark.unit
FACE = UUID("00000000-0000-4000-8000-000000000001")


def provider(monkeypatch: pytest.MonkeyPatch, response: httpx.Response):
    requests: list[httpx.Request] = []
    constructor = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return response

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: constructor(transport=httpx.MockTransport(handler), **kwargs),
    )
    return requests


async def test_compose_uses_pcm16_v2_and_finite_mode_bounds(monkeypatch):
    requests = provider(
        monkeypatch, httpx.Response(200, json={"session_token": "test-opaque-token"})
    )
    assert await SimliClient("test-only-credential").token(FACE) == "test-opaque-token"
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://api.simli.ai/compose/token"
    assert json.loads(requests[0].content) == {
        "faceId": str(FACE),
        "apiVersion": "v2",
        "handleSilence": True,
        "maxSessionLength": settings.avatar_session_length_seconds,
        "maxIdleTime": settings.avatar_idle_seconds,
        "audioInputFormat": "pcm16",
        "startFrame": 0,
    }


async def test_empty_private_faces_is_valid_and_does_not_create_a_session(monkeypatch):
    requests = provider(monkeypatch, httpx.Response(200, json=[]))
    assert await SimliClient("test-only-credential").faces() == []
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/faces"),
        ("GET", "/auto/agents"),
    ]


async def test_account_avatars_are_listed_even_when_private_faces_is_empty(monkeypatch):
    constructor = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/faces":
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {
                    "face_id": str(FACE),
                    "name": "Impressed Tiger",
                    "prompt": "private prompt must never leave the client",
                }
            ],
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: constructor(transport=httpx.MockTransport(handler), **kw)
    )
    faces = await SimliClient("test-only-credential").faces()
    assert [(face.id, face.name) for face in faces] == [(FACE, "Impressed Tiger")]
    assert "prompt" not in faces[0].model_dump()
    assert all(request.method == "GET" for request in requests)


@pytest.mark.parametrize("failed_path", ["/faces", "/auto/agents"])
async def test_failed_catalogue_does_not_hide_the_other_account_catalogue(monkeypatch, failed_path):
    constructor = httpx.AsyncClient

    def handler(request):
        if request.url.path == failed_path:
            return httpx.Response(503, json={})
        item = (
            {"id": str(FACE), "name": "Custom face"}
            if failed_path == "/auto/agents"
            else {"face_id": str(FACE), "name": "Account avatar"}
        )
        return httpx.Response(200, json=[item])

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: constructor(transport=httpx.MockTransport(handler), **kw)
    )
    faces = await SimliClient("test-only-credential").faces()
    assert [face.id for face in faces] == [FACE]


@pytest.mark.parametrize(
    "status,payload", [(500, {}), (200, {}), (302, {}), (200, {"session_token": "x" * 8193})]
)
async def test_bad_mint_is_never_retried_or_returned_as_a_credential(monkeypatch, status, payload):
    requests = provider(monkeypatch, httpx.Response(status, json=payload))
    with pytest.raises(SimliError) as raised:
        await SimliClient("test-only-credential").token(FACE)
    assert "test-only-credential" not in str(raised.value)
    assert len(requests) == 1


async def test_closed_session_confirmation_uses_provider_current_usage(monkeypatch):
    requests = provider(monkeypatch, httpx.Response(200, json={"currentUsage": 0}))
    assert await SimliClient("test-only-credential").active_count() == 0
    assert [(r.method, r.url.path) for r in requests] == [("GET", "/ratelimiter/sessions")]
