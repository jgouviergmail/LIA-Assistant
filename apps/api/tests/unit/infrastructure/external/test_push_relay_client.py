"""
The calling side of the relay: what a self-hosted server concludes from it.

One rule dominates every other assertion here — **doubt never deletes**. A
relay that is unreachable, slow, broken, or answering something this client has
never seen must produce "not sent, keep the handle". The only thing that may
cost a user their notifications is the relay explicitly saying the handle can
never work again.

That asymmetry is deliberate: the cost of keeping a dead handle is one wasted
HTTP call per notification, and the cost of dropping a live one is silence on a
phone until its owner happens to relaunch the app.
"""

from __future__ import annotations

import httpx
import pytest

from src.infrastructure.external.push_relay_client import PushRelayClient

pytestmark = pytest.mark.unit


def _client(handler: object) -> PushRelayClient:
    return PushRelayClient(
        base_url="https://relay.example.com",
        timeout=5.0,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


def _answers(status: int, body: object) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, request=request)

    return handler


class TestRequestShape:
    async def test_it_posts_the_handle_to_the_relay_s_wake_endpoint(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200, json={"outcome": "sent", "should_forget_handle": False}, request=request
            )

        await _client(handler).wake("sealed-handle")

        assert str(seen[0].url) == "https://relay.example.com/api/v1/push-relay/wake"
        assert seen[0].read() == b'{"handle":"sealed-handle"}'

    async def test_a_trailing_slash_on_the_configured_url_is_harmless(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200, json={"outcome": "sent", "should_forget_handle": False}, request=request
            )

        client = PushRelayClient(
            base_url="https://relay.example.com/",
            timeout=5.0,
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        )
        await client.wake("sealed-handle")

        # An operator pasting a URL with a slash should not silently produce a
        # double slash that some proxies answer 404 to.
        assert "//api" not in str(seen[0].url).removeprefix("https://")


class TestVerdicts:
    async def test_a_sent_wake_is_a_sent_wake(self) -> None:
        result = await _client(
            _answers(200, {"outcome": "sent", "should_forget_handle": False})
        ).wake("h")

        assert result.sent is True
        assert result.should_forget_handle is False

    async def test_the_relay_saying_forget_is_obeyed(self) -> None:
        result = await _client(
            _answers(200, {"outcome": "device_gone", "should_forget_handle": True})
        ).wake("h")

        assert result.sent is False
        assert result.should_forget_handle is True


class TestDoubtNeverDeletes:
    async def test_an_unreachable_relay_keeps_the_handle(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        result = await _client(handler).wake("h")

        assert result.sent is False
        assert result.should_forget_handle is False

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    async def test_a_relay_in_trouble_keeps_the_handle(self, status: int) -> None:
        result = await _client(_answers(status, {"detail": "nope"})).wake("h")

        assert result.sent is False
        assert result.should_forget_handle is False

    async def test_an_answer_we_cannot_parse_keeps_the_handle(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>hello</html>", request=request)

        result = await _client(handler).wake("h")

        # A relay that started answering HTML is a relay we no longer
        # understand — not a verdict on anybody's device.
        assert result.sent is False
        assert result.should_forget_handle is False

    async def test_a_missing_flag_is_read_as_keep_it(self) -> None:
        result = await _client(_answers(200, {"outcome": "sent"})).wake("h")

        # An older or newer relay omitting the field must not be read as
        # permission to delete.
        assert result.should_forget_handle is False

    async def test_a_404_does_not_mean_the_handle_is_gone(self) -> None:
        result = await _client(_answers(404, {"detail": "not found"})).wake("h")

        # A 404 here says the RELAY's route is wrong — a deployment mistake of
        # ours, and reading it as "device gone" would delete every handle.
        assert result.should_forget_handle is False
