"""Every request of the library is checked at every hop (ADR-327, ADR-326).

A redirect is a new URL, validated before it is contacted; a private address
behind a redirect is refused; a credential never leaves the host it was given
for; GitHub's spent allowance is told apart from a failure; a body past the
ceiling is refused; a failure is an outcome, never an exception.
"""

from __future__ import annotations

import httpx
import pytest

from src.domains.agents.web_fetch import url_validator
from src.domains.skill_library.http import FetchOutcome, fetch

pytestmark = pytest.mark.unit


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _host(request: httpx.Request) -> str:
    return request.headers.get("host", request.url.host)


class TestRedirects:
    async def test_a_redirect_is_followed_once_validated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if _host(request) == "api.github.com":
                return httpx.Response(301, headers={"location": "https://api2.github.com/x"})
            return httpx.Response(200, content=b"moved")

        async with _client(handler) as client:
            answer = await fetch(client, "https://api.github.com/repos/o/r")
        assert answer.outcome is FetchOutcome.OK and answer.body == b"moved"

    async def test_a_redirect_to_a_private_address_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            url_validator,
            "_resolve_dns_sync",
            lambda host: ["10.0.0.5"] if host == "internal.example" else ["93.184.216.34"],
        )
        contacted: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            contacted.append(_host(request))
            return httpx.Response(302, headers={"location": "https://internal.example/admin"})

        async with _client(handler) as client:
            answer = await fetch(client, "https://api.github.com/repos/o/r")
        assert answer.outcome is FetchOutcome.BLOCKED
        assert contacted == ["api.github.com"]

    async def test_a_credential_stays_with_its_host(self) -> None:
        received: dict[str, str | None] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received[_host(request)] = request.headers.get("authorization")
            if _host(request) == "api.github.com":
                return httpx.Response(302, headers={"location": "https://elsewhere.example/x"})
            return httpx.Response(200, content=b"x")

        async with _client(handler) as client:
            await fetch(client, "https://api.github.com/x", headers={"Authorization": "Bearer t"})
        assert received == {"api.github.com": "Bearer t", "elsewhere.example": None}

    async def test_an_endless_redirect_ends(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://loop.example/again"})

        async with _client(handler) as client:
            assert (await fetch(client, "https://loop.example/")).outcome is FetchOutcome.BLOCKED


class TestOutcomes:
    @pytest.mark.parametrize(
        ("response", "outcome"),
        [
            (httpx.Response(404), FetchOutcome.NOT_FOUND),
            (httpx.Response(500), FetchOutcome.HTTP_ERROR),
            (httpx.Response(429), FetchOutcome.RATE_LIMITED),
            (
                httpx.Response(403, headers={"x-ratelimit-remaining": "0"}),
                FetchOutcome.RATE_LIMITED,
            ),
            (httpx.Response(403), FetchOutcome.HTTP_ERROR),
        ],
        ids=["404", "500", "429", "403-spent", "403-forbidden"],
    )
    async def test_each_answer_is_named(
        self, response: httpx.Response, outcome: FetchOutcome
    ) -> None:
        async with _client(lambda _r: response) as client:
            assert (await fetch(client, "https://api.github.com/x")).outcome is outcome

    async def test_the_reset_instant_travels_with_a_spent_allowance(self) -> None:
        answer = httpx.Response(
            403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "123"}
        )
        async with _client(lambda _r: answer) as client:
            assert (await fetch(client, "https://api.github.com/x")).reset_at == 123

    async def test_a_body_past_the_ceiling_is_refused(self) -> None:
        async with _client(lambda _r: httpx.Response(200, content=b"x" * 11)) as client:
            answer = await fetch(client, "https://api.github.com/x", max_bytes=10)
        assert answer.outcome is FetchOutcome.TOO_LARGE

    async def test_a_transport_failure_is_an_outcome(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        async with _client(handler) as client:
            assert (await fetch(client, "https://api.github.com/x")).outcome is (
                FetchOutcome.UNREACHABLE
            )

    async def test_plain_http_is_never_requested(self) -> None:
        contacted: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            contacted.append(str(request.url))
            return httpx.Response(200)

        async with _client(handler) as client:
            answer = await fetch(client, "http://api.github.com/x")
        # The validator upgrades http to https: what leaves is https, never plain.
        assert all(url.startswith("https://") for url in contacted)
        assert answer.outcome is FetchOutcome.OK
