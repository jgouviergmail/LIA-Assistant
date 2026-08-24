"""
The APNs provider client — what it sends, and what it concludes.

Apple is the only route to an iPhone, and it answers with a status plus a
machine-readable reason. Every one of those reasons means one of exactly four
things to a caller: Apple took it, this device no longer exists, we are
misconfigured, or come back later. Collapsing them wrongly is how a dead device
gets retried forever, or a live one gets deleted — so the mapping is pinned
here, reason by reason.

Two properties beyond the mapping matter and are asserted directly: the
provider token is a real ES256 JWT carrying the key id in its header (Apple
rejects anything else), and it is REUSED between sends. Apple refuses providers
that mint a fresh token per request.

No network: an ``httpx.MockTransport`` answers, which is also what lets the
request itself — host, path, headers — be the subject of assertions rather than
an assumption.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.infrastructure.external.apns_client import (
    ApnsClient,
    ApnsCredentials,
    ApnsDeliveryStatus,
)

pytestmark = pytest.mark.unit


def _signing_key() -> str:
    """A throwaway P-256 key in the PKCS#8 PEM shape Apple's .p8 files use."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def credentials() -> ApnsCredentials:
    return ApnsCredentials(
        key_pem=_signing_key(),
        key_id="ABCDE12345",
        team_id="TEAM123456",
        topic="com.lia.assistant",
        sandbox=False,
    )


def _client(
    credentials: ApnsCredentials,
    handler: Any,
    *,
    now: Any = None,
) -> ApnsClient:
    transport = httpx.MockTransport(handler)
    return ApnsClient(credentials, transport=transport, now=now)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, request=request)


def _refused(status: int, reason: str) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"reason": reason}, request=request)

    return handler


class TestRequestShape:
    """What actually goes to Apple."""

    async def test_targets_the_production_host_and_the_device_path(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("dead-beef-token", {"aps": {"alert": "hi"}})

        assert str(seen[0].url) == "https://api.push.apple.com/3/device/dead-beef-token"

    async def test_targets_the_sandbox_host_when_configured(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        sandbox = replace(credentials, sandbox=True)
        client = _client(sandbox, handler)
        await client.send("tok", {"aps": {}})

        # A production token is meaningless to the sandbox gateway and the other
        # way round: the wrong host is silently "BadDeviceToken" forever.
        assert str(seen[0].url).startswith("https://api.sandbox.push.apple.com/")

    async def test_carries_the_topic_and_the_push_type(self, credentials: ApnsCredentials) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("tok", {"aps": {}}, collapse_id="wake")

        headers = seen[0].headers
        assert headers["apns-topic"] == "com.lia.assistant"
        assert headers["apns-push-type"] == "alert"
        assert headers["apns-collapse-id"] == "wake"

    async def test_sends_the_payload_verbatim(self, credentials: ApnsCredentials) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("tok", {"aps": {"alert": {"title": "T", "body": "B"}}})

        assert json.loads(seen[0].content) == {"aps": {"alert": {"title": "T", "body": "B"}}}


class TestProviderToken:
    """The bearer Apple checks on every request."""

    async def test_is_an_es256_jwt_naming_the_team_and_the_key(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("tok", {"aps": {}})

        raw = seen[0].headers["authorization"].removeprefix("bearer ")
        assert jwt.get_unverified_header(raw) == {
            "alg": "ES256",
            "kid": "ABCDE12345",
            "typ": "JWT",
        }
        claims = jwt.decode(raw, options={"verify_signature": False})
        assert claims["iss"] == "TEAM123456"
        assert "iat" in claims

    async def test_is_reused_between_sends(self, credentials: ApnsCredentials) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("tok-1", {"aps": {}})
        await client.send("tok-2", {"aps": {}})

        # Apple rate-limits providers that mint a token per request: a fresh
        # signature every time is itself a rejection cause.
        assert seen[0].headers["authorization"] == seen[1].headers["authorization"]

    async def test_is_renewed_once_it_ages_past_the_window(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []
        clock = {"value": datetime(2026, 8, 24, 12, 0, tzinfo=UTC)}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler, now=lambda: clock["value"])
        await client.send("tok-1", {"aps": {}})
        clock["value"] += timedelta(minutes=55)
        await client.send("tok-2", {"aps": {}})

        # Apple refuses a token older than an hour, so the renewal has to happen
        # before that — not on the rejection.
        assert seen[0].headers["authorization"] != seen[1].headers["authorization"]


class TestVerdicts:
    """Four conclusions, and which of Apple's answers lead to each."""

    async def test_a_200_is_accepted_not_delivered(self, credentials: ApnsCredentials) -> None:
        client = _client(credentials, _ok)
        result = await client.send("tok", {"aps": {}})

        # Apple took custody. Whether the phone ever showed it is not something
        # this response can say, and the name must not pretend otherwise.
        assert result.status is ApnsDeliveryStatus.ACCEPTED
        assert result.reason is None

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (410, "Unregistered"),
            (400, "BadDeviceToken"),
        ],
    )
    async def test_a_dead_device_is_reported_as_gone(
        self, credentials: ApnsCredentials, status: int, reason: str
    ) -> None:
        client = _client(credentials, _refused(status, reason))
        result = await client.send("tok", {"aps": {}})

        assert result.status is ApnsDeliveryStatus.DEVICE_GONE
        assert result.reason == reason

    @pytest.mark.parametrize(
        "reason",
        ["DeviceTokenNotForTopic", "TopicDisallowed", "InvalidProviderToken"],
    )
    async def test_our_own_misconfiguration_is_not_the_device_s_fault(
        self, credentials: ApnsCredentials, reason: str
    ) -> None:
        client = _client(credentials, _refused(400, reason))
        result = await client.send("tok", {"aps": {}})

        # Deleting the device here would be destroying evidence of OUR bug, and
        # every other device would fail the same way.
        assert result.status is ApnsDeliveryStatus.REJECTED

    @pytest.mark.parametrize("status", [429, 500, 503])
    async def test_apple_asking_for_later_is_not_a_verdict_on_the_device(
        self, credentials: ApnsCredentials, status: int
    ) -> None:
        client = _client(credentials, _refused(status, "ServiceUnavailable"))
        result = await client.send("tok", {"aps": {}})

        assert result.status is ApnsDeliveryStatus.UNAVAILABLE

    async def test_a_transport_failure_is_unavailable_not_rejected(
        self, credentials: ApnsCredentials
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        client = _client(credentials, handler)
        result = await client.send("tok", {"aps": {}})

        assert result.status is ApnsDeliveryStatus.UNAVAILABLE

    async def test_an_unparsable_refusal_still_yields_a_verdict(
        self, credentials: ApnsCredentials
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, content=b"<html>nope</html>", request=request)

        client = _client(credentials, handler)
        result = await client.send("tok", {"aps": {}})

        # An unknown 4xx is ours to fix, not the device's to die for.
        assert result.status is ApnsDeliveryStatus.REJECTED


class TestExpiredProviderToken:
    """The one refusal that is worth retrying immediately."""

    async def test_a_stale_token_is_renewed_and_the_send_retried_once(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if len(seen) == 1:
                return httpx.Response(403, json={"reason": "ExpiredProviderToken"}, request=request)
            return _ok(request)

        client = _client(credentials, handler)
        result = await client.send("tok", {"aps": {}})

        assert result.status is ApnsDeliveryStatus.ACCEPTED
        assert len(seen) == 2
        assert seen[0].headers["authorization"] != seen[1].headers["authorization"]

    async def test_it_is_retried_only_once(self, credentials: ApnsCredentials) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(403, json={"reason": "ExpiredProviderToken"}, request=request)

        client = _client(credentials, handler)
        result = await client.send("tok", {"aps": {}})

        # Renewing forever against a clock-skewed server is a retry storm with
        # a signature cost attached.
        assert len(seen) == 2
        assert result.status is ApnsDeliveryStatus.REJECTED


class TestPerSendGateway:
    """One client, both of Apple's gateways.

    The relay serves devices from production builds and from development ones,
    and which gateway a token belongs to is a property of the DEVICE. The
    provider token is team-scoped and valid on both, so overriding the host per
    send avoids running two clients that each mint their own JWT.
    """

    async def test_a_send_can_override_the_gateway(self, credentials: ApnsCredentials) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(credentials, handler)
        await client.send("tok", {"aps": {}}, sandbox=True)

        assert str(seen[0].url).startswith("https://api.sandbox.push.apple.com/")

    async def test_not_overriding_it_keeps_the_credentials_setting(
        self, credentials: ApnsCredentials
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(request)

        client = _client(replace(credentials, sandbox=True), handler)
        await client.send("tok", {"aps": {}})

        assert str(seen[0].url).startswith("https://api.sandbox.push.apple.com/")


class TestConnectionOwnership:
    """Apple asks providers to keep the connection open — so it needs an owner.

    A client per notification means a TLS and HTTP/2 handshake per push, which
    is both slow and something Apple throttles. Holding one open is the
    correct behaviour and creates the obligation these tests pin: it must be
    reused, and it must be closeable.
    """

    async def test_one_connection_serves_many_sends(self, credentials: ApnsCredentials) -> None:
        client = _client(credentials, _ok)
        await client.send("tok-1", {"aps": {}})
        first = client._http()
        await client.send("tok-2", {"aps": {}})

        assert client._http() is first

    async def test_closing_releases_it(self, credentials: ApnsCredentials) -> None:
        client = _client(credentials, _ok)
        await client.send("tok", {"aps": {}})

        await client.aclose()

        # An unclosed transport is a test failure in this repository, and a
        # leaked socket in production.
        assert client._client is None

    async def test_closing_twice_is_harmless(self, credentials: ApnsCredentials) -> None:
        client = _client(credentials, _ok)

        await client.aclose()
        await client.aclose()

    async def test_it_reopens_after_a_close(self, credentials: ApnsCredentials) -> None:
        client = _client(credentials, _ok)
        await client.send("tok", {"aps": {}})
        await client.aclose()

        result = await client.send("tok", {"aps": {}})

        # Shutdown is not the only caller: a relay that closed and kept running
        # must not answer UNAVAILABLE forever.
        assert result.status is ApnsDeliveryStatus.ACCEPTED
