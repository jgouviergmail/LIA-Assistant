"""Global request-body ceiling — SEC-031.

Endpoints used to validate their payload *after* materialising it (``await
request.body()`` on the Telegram and telephony webhooks, ``await file.read()``
on attachments and skill imports, the health-metrics batch), so the peak memory
of a request was chosen by the client. On the webhooks that happened before
authentication, making it reachable without credentials.

These tests exercise the middleware through a real ASGI app rather than by
poking at its internals: what matters is the contract seen by a client and by a
handler, not the shape of the implementation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.middleware import BodySizeLimitMiddleware


@pytest.fixture
def limit_bytes() -> int:
    """A small ceiling keeps the tests fast and the payloads readable."""
    return 1024


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, limit_bytes: int) -> TestClient:
    """An app whose only middleware is the one under test."""
    monkeypatch.setattr(
        "src.core.middleware.settings.max_request_body_bytes", limit_bytes, raising=False
    )

    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        """A handler that reads the whole body, like the audited endpoints did."""
        body = await request.body()
        return {"received": len(body)}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


class TestBodiesWithinTheCeiling:
    """The nominal path must be untouched."""

    def test_small_body_reaches_the_handler(self, client: TestClient):
        """A normal payload is delivered in full."""
        response = client.post("/echo", content=b"x" * 100)

        assert response.status_code == 200
        assert response.json() == {"received": 100}

    def test_body_exactly_at_the_ceiling_is_accepted(self, client: TestClient, limit_bytes: int):
        """The limit is inclusive — N bytes pass, N+1 do not.

        Pins the boundary explicitly: an off-by-one here would reject the
        largest legitimate upload, which is exactly the regression a size guard
        tends to introduce.
        """
        response = client.post("/echo", content=b"x" * limit_bytes)

        assert response.status_code == 200
        assert response.json() == {"received": limit_bytes}

    def test_empty_body_is_accepted(self, client: TestClient):
        """A bodyless POST is not a size violation."""
        response = client.post("/echo", content=b"")

        assert response.status_code == 200
        assert response.json() == {"received": 0}

    def test_get_requests_are_unaffected(self, client: TestClient):
        """Requests without a body pass straight through."""
        assert client.get("/ping").json() == {"ok": True}


class TestBodiesOverTheCeiling:
    """Oversized requests are refused with a usable answer."""

    def test_declared_length_over_the_limit_is_refused(self, client: TestClient, limit_bytes: int):
        """A truthful, oversized Content-Length is refused up front."""
        response = client.post("/echo", content=b"x" * (limit_bytes + 1))

        assert response.status_code == 413
        assert response.json()["detail"] == "Request body too large"

    def test_handler_never_runs_for_an_oversized_body(self, client: TestClient, limit_bytes: int):
        """The refusal is not the handler's — the body never reaches it."""
        response = client.post("/echo", content=b"x" * (limit_bytes * 4))

        assert response.status_code == 413
        # A handler that had run would answer 200 with a `received` count.
        assert "received" not in response.json()

    def test_chunked_body_over_the_limit_is_cut(self, client: TestClient, limit_bytes: int):
        """A chunked body carries no Content-Length — only counting catches it.

        This is the case the header check cannot see, and the reason the byte
        counter exists rather than trusting the declared length.
        """

        def oversized_chunks():
            for _ in range(10):
                yield b"y" * limit_bytes

        response = client.post("/echo", content=oversized_chunks())

        assert response.status_code == 413

    def test_understated_content_length_is_still_caught(self, client: TestClient, limit_bytes: int):
        """A client lying about its length gains nothing.

        The header says "small", the stream delivers large. Trusting the header
        would let this through, which is why it is treated as a hint only.
        """

        def liar():
            yield b"z" * (limit_bytes * 3)

        response = client.post(
            "/echo",
            content=liar(),
            headers={"content-length": "10"},
        )

        assert response.status_code == 413


class TestMalformedHeaders:
    """A broken Content-Length must not crash or bypass the guard."""

    @pytest.mark.parametrize("value", ["abc", "-1", "", "1e9", "12 34"])
    def test_invalid_content_length_falls_back_to_counting(
        self, client: TestClient, limit_bytes: int, value: str
    ):
        """An unparseable header is ignored; the byte counter still applies.

        Rejecting on a malformed header would be a denial-of-service of its own
        (any proxy quirk becomes a 413), so the guard degrades to counting.
        """
        response = client.post(
            "/echo",
            content=b"x" * (limit_bytes + 1),
            headers={"content-length": value},
        )

        # Either the transport normalises the header and we refuse on the
        # declared length, or we refuse after counting — never a 500, never a
        # pass-through.
        assert response.status_code == 413


class TestNonHttpScopes:
    """Only HTTP requests are wrapped."""

    @pytest.mark.asyncio
    async def test_websocket_scope_passes_through_untouched(self):
        """A WebSocket scope must reach the app with the ORIGINAL receive.

        Wrapping it would count frames against an HTTP body ceiling and close
        long-lived connections — the voice transcription socket, for one.
        """
        seen: dict[str, object] = {}

        async def app(scope, receive, send):
            seen["scope_type"] = scope["type"]
            seen["receive"] = receive

        middleware = BodySizeLimitMiddleware(app)

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            return None

        await middleware({"type": "websocket", "path": "/ws/audio"}, receive, send)

        assert seen["scope_type"] == "websocket"
        assert seen["receive"] is receive, "the receive callable must not be wrapped"

    @pytest.mark.asyncio
    async def test_lifespan_scope_passes_through(self):
        """Startup/shutdown must not be intercepted."""
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        middleware = BodySizeLimitMiddleware(app)

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(message):
            return None

        await middleware({"type": "lifespan"}, receive, send)

        assert called
