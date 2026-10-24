"""The one exchange of a refresh token, and what each provider answer means (audit AC-029).

Every refresh path used to carry its own POST: the legacy connectors, the shared grants
and the Hue bridge each parsed the answer their own way. One exchange now speaks for
all of them, so the refusal that disconnects a person (``invalid_grant``) has one
reading, and a rate limit or an outage is never mistaken for it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from functools import partial

import httpx
import pytest
from tenacity import wait_none

from src.core.config import settings
from src.domains.connectors import oauth_refresh_exchange as exchange
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshRefusal,
    RefreshRefused,
    TokenEndpoint,
    exchange_refresh_token,
)

pytestmark = pytest.mark.unit

_ENDPOINT = TokenEndpoint(
    url="https://tokens.example.test/token",
    client_id="client-id",
    client_secret="client-secret",
    sends_scope=False,
    basic_auth=False,
)


class _Provider:
    """A token endpoint that answers what a test scripts, and records each request."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self._answers: Iterator[httpx.Response | Exception] = iter(answers)
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = next(self._answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _Provider]:
    """Install a scripted provider behind the exchange's own HTTP client."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(exchange, "_retry_wait", wait_none)

    def install(*answers: httpx.Response | Exception) -> _Provider:
        scripted = _Provider(*answers)
        transport = httpx.MockTransport(scripted.handle)
        monkeypatch.setattr(httpx, "AsyncClient", partial(real_client, transport=transport))
        return scripted

    return install


def _form(request: httpx.Request) -> dict[str, str]:
    return dict(httpx.QueryParams(request.content.decode()))


async def _exchange(endpoint: TokenEndpoint = _ENDPOINT, scopes: tuple[str, ...] = ()) -> object:
    return await exchange_refresh_token(
        endpoint, refresh_token="sent-refresh", scopes=scopes, owner_id=None
    )


class TestASuccessfulExchange:
    async def test_a_rotated_refresh_token_replaces_the_one_sent(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(
            httpx.Response(
                200,
                json={
                    "access_token": "fresh",
                    "refresh_token": "rotated",
                    "expires_in": 3599,
                    "scope": "a b",
                },
            )
        )
        before = datetime.now(UTC)

        token = await exchange_refresh_token(
            _ENDPOINT, refresh_token="sent-refresh", scopes=(), owner_id=None
        )

        assert (token.access_token, token.refresh_token) == ("fresh", "rotated")
        assert token.reported_scopes == frozenset({"a", "b"})
        assert before + timedelta(seconds=3599) <= token.expires_at
        assert token.expires_at <= datetime.now(UTC) + timedelta(seconds=3599)

    async def test_a_provider_that_keeps_the_refresh_token_keeps_the_one_sent(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(httpx.Response(200, json={"access_token": "fresh", "expires_in": 60}))

        token = await exchange_refresh_token(
            _ENDPOINT, refresh_token="sent-refresh", scopes=(), owner_id=None
        )

        assert token.refresh_token == "sent-refresh"
        assert token.reported_scopes == frozenset()

    async def test_an_answer_without_a_lifetime_lives_the_default_hour(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(httpx.Response(200, json={"access_token": "fresh"}))

        token = await exchange_refresh_token(
            _ENDPOINT, refresh_token="sent-refresh", scopes=(), owner_id=None
        )

        assert token.expires_at > datetime.now(UTC) + timedelta(minutes=59)


class TestWhatTheRequestCarries:
    async def test_a_client_secret_travels_in_the_form(
        self, provider: Callable[..., _Provider]
    ) -> None:
        scripted = provider(httpx.Response(200, json={"access_token": "fresh"}))

        await exchange_refresh_token(
            _ENDPOINT, refresh_token="sent-refresh", scopes=("s1",), owner_id=None
        )

        form = _form(scripted.requests[0])
        assert form == {
            "grant_type": "refresh_token",
            "refresh_token": "sent-refresh",
            "client_id": "client-id",
            "client_secret": "client-secret",
        }

    async def test_an_endpoint_that_requires_the_scopes_receives_them(
        self, provider: Callable[..., _Provider]
    ) -> None:
        scripted = provider(httpx.Response(200, json={"access_token": "fresh"}))
        endpoint = TokenEndpoint(
            url=_ENDPOINT.url,
            client_id="id",
            client_secret="secret",
            sends_scope=True,
            basic_auth=False,
        )

        await exchange_refresh_token(
            endpoint, refresh_token="sent-refresh", scopes=("s1", "s2"), owner_id=None
        )

        assert _form(scripted.requests[0])["scope"] == "s1 s2"

    async def test_a_basic_auth_client_keeps_its_secret_out_of_the_form(
        self, provider: Callable[..., _Provider]
    ) -> None:
        scripted = provider(httpx.Response(200, json={"access_token": "fresh"}))
        endpoint = TokenEndpoint(
            url=_ENDPOINT.url,
            client_id="id",
            client_secret="secret",
            sends_scope=False,
            basic_auth=True,
        )

        await exchange_refresh_token(
            endpoint, refresh_token="sent-refresh", scopes=(), owner_id=None
        )

        request = scripted.requests[0]
        assert _form(request) == {"grant_type": "refresh_token", "refresh_token": "sent-refresh"}
        assert request.headers["authorization"].startswith("Basic ")


class TestARefusalHasOneReading:
    @pytest.mark.parametrize("code", ["invalid_grant", "interaction_required"])
    async def test_a_revoked_grant_is_a_revocation(
        self, provider: Callable[..., _Provider], code: str
    ) -> None:
        provider(httpx.Response(400, json={"error": code}))

        with pytest.raises(RefreshRefused) as refused:
            await _exchange()

        assert refused.value.reason is RefreshRefusal.REVOKED
        assert refused.value.status_code == 400

    async def test_a_client_the_provider_refuses_is_not_the_person_s_revocation(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(httpx.Response(401, json={"error": "invalid_client"}))

        with pytest.raises(RefreshRefused) as refused:
            await _exchange()

        assert refused.value.reason is RefreshRefusal.TRANSIENT

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(503, json={"error": "temporarily_unavailable"}),
            httpx.Response(429, json={"error": "rate_limited"}),
            httpx.ConnectError("unreachable"),
        ],
        ids=["outage", "rate-limit", "network"],
    )
    async def test_an_outage_is_retried_then_transient(
        self, provider: Callable[..., _Provider], answer: httpx.Response | Exception
    ) -> None:
        scripted = provider(*([answer] * exchange.OAUTH_REFRESH_ATTEMPTS))

        with pytest.raises(RefreshRefused) as refused:
            await _exchange()

        assert refused.value.reason is RefreshRefusal.TRANSIENT
        assert len(scripted.requests) == exchange.OAUTH_REFRESH_ATTEMPTS

    async def test_an_outage_that_clears_is_a_success(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(httpx.Response(503), httpx.Response(200, json={"access_token": "fresh"}))

        token = await exchange_refresh_token(
            _ENDPOINT, refresh_token="sent-refresh", scopes=(), owner_id=None
        )

        assert token.access_token == "fresh"

    @pytest.mark.parametrize(
        "body",
        [
            {"expires_in": 60},
            {"access_token": "", "expires_in": 60},
            {"access_token": "fresh", "expires_in": "60"},
            {"access_token": "fresh", "expires_in": 0},
            {"access_token": "fresh", "scope": ["a"]},
            ["not", "an", "object"],
        ],
        ids=["no-token", "empty-token", "string-lifetime", "zero-lifetime", "list-scope", "list"],
    )
    async def test_a_success_without_a_usable_token_is_unreadable(
        self, provider: Callable[..., _Provider], body: object
    ) -> None:
        provider(httpx.Response(200, json=body))

        with pytest.raises(RefreshRefused) as refused:
            await _exchange()

        assert refused.value.reason is RefreshRefusal.UNREADABLE

    async def test_a_success_that_is_not_json_is_unreadable(
        self, provider: Callable[..., _Provider]
    ) -> None:
        provider(httpx.Response(200, content=b"<html>"))

        with pytest.raises(RefreshRefused) as refused:
            await _exchange()

        assert refused.value.reason is RefreshRefusal.UNREADABLE


def test_the_worst_case_is_derived_from_the_retry_policy() -> None:
    """Whoever waits for an exchange is bounded by what the exchange may take."""
    waits = sum(
        min(
            max(exchange.OAUTH_REFRESH_WAIT_MIN_SECONDS, 2 ** (attempt - 1)),
            exchange.OAUTH_REFRESH_WAIT_MAX_SECONDS,
        )
        for attempt in range(1, exchange.OAUTH_REFRESH_ATTEMPTS)
    )
    expected = exchange.OAUTH_REFRESH_ATTEMPTS * settings.http_timeout_oauth + waits

    assert exchange.worst_case_refresh_seconds() == expected
