"""The client IP must come from a header the client cannot write.

Production runs uvicorn with ``--proxy-headers --forwarded-allow-ips "*"``, which
makes uvicorn REWRITE ``scope["client"]`` from ``X-Forwarded-For``. With every
hop trusted, it keeps the LEFTMOST entry — and the leftmost entry is the one the
visitor supplied, because Cloudflare APPENDS the real address rather than
replacing the header.

Reproduced in an isolated container on 2026-08-05, replaying the production
topology::

    curl -H "X-Forwarded-For: 127.0.0.1, 198.51.100.42" .../whoami
    -> {"resolved_client": "127.0.0.1", "xff_header": "127.0.0.1, 198.51.100.42"}

Two consequences, both observed: the global rate limit buckets on a value the
caller chooses, so rotating it mints a fresh 300-requests-per-minute budget at
will; and the audit trail is poisoned — the 2600 rate-limit warnings of the
2026-07-30 scan were all recorded as ``geo_country=local`` because the scanner
declared itself as loopback.

``CF-Connecting-IP`` carries a single address and is written by Cloudflare, which
overwrites whatever the visitor sent. It is trustworthy here for the same reason
the deployment already documents for ``forwarded-allow-ips``: the published port
is loopback-bound, so the only peers that can reach uvicorn are cloudflared, the
in-container healthcheck and compose-internal services.
"""

from __future__ import annotations

import pytest

from src.core.client_ip import UNKNOWN_CLIENT_IP, resolve_client_ip

pytestmark = pytest.mark.unit


def _scope(headers: list[tuple[bytes, bytes]] | None = None, client: tuple | None = None) -> dict:
    """A minimal ASGI scope, shaped as Starlette delivers it."""
    return {"type": "http", "headers": headers or [], "client": client}


class TestTheTrustedHeaderWins:
    """Cloudflare's header is the only one the visitor cannot author."""

    def test_cf_connecting_ip_is_preferred_over_the_rewritten_peer(self) -> None:
        scope = _scope(
            headers=[
                (b"x-forwarded-for", b"127.0.0.1, 198.51.100.42"),
                (b"cf-connecting-ip", b"198.51.100.42"),
            ],
            client=("127.0.0.1", 51234),  # what uvicorn resolved from the forged XFF
        )

        assert resolve_client_ip(scope) == "198.51.100.42"

    def test_a_forged_x_forwarded_for_cannot_win(self) -> None:
        """The exact production attack: declare yourself loopback, keep your budget."""
        scope = _scope(
            headers=[
                (b"x-forwarded-for", b"127.0.0.1"),
                (b"cf-connecting-ip", b"203.0.113.99"),
            ],
            client=("127.0.0.1", 51234),
        )

        assert resolve_client_ip(scope) == "203.0.113.99"

    def test_header_lookup_is_case_insensitive(self) -> None:
        """HTTP/2 lowercases, HTTP/1.1 does not — both must resolve."""
        scope = _scope(headers=[(b"CF-Connecting-IP", b"203.0.113.7")], client=("10.0.0.1", 1))

        assert resolve_client_ip(scope) == "203.0.113.7"

    def test_surrounding_whitespace_is_ignored(self) -> None:
        scope = _scope(headers=[(b"cf-connecting-ip", b"  203.0.113.7  ")], client=None)

        assert resolve_client_ip(scope) == "203.0.113.7"


class TestFallbackWhenCloudflareIsAbsent:
    """Dev and direct calls have no Cloudflare hop; behaviour must not regress."""

    def test_peer_address_is_used_without_the_header(self) -> None:
        scope = _scope(client=("192.168.0.30", 4242))

        assert resolve_client_ip(scope) == "192.168.0.30"

    def test_an_empty_header_falls_back(self) -> None:
        """A header present but blank must not resolve to an empty bucket key."""
        scope = _scope(headers=[(b"cf-connecting-ip", b"   ")], client=("192.168.0.30", 4242))

        assert resolve_client_ip(scope) == "192.168.0.30"

    def test_no_peer_and_no_header_is_explicit(self) -> None:
        assert resolve_client_ip(_scope()) == UNKNOWN_CLIENT_IP


class TestMalformedHeadersNeverWin:
    """A value that is not an address must not become a rate-limit bucket."""

    @pytest.mark.parametrize(
        "value",
        [
            b"not-an-ip",
            b"203.0.113.99, 198.51.100.42",  # a list: never what Cloudflare sends
            b"<script>",
            b"999.999.999.999",
        ],
        ids=["garbage", "list", "injection", "out-of-range"],
    )
    def test_invalid_value_falls_back_to_the_peer(self, value: bytes) -> None:
        scope = _scope(headers=[(b"cf-connecting-ip", value)], client=("192.168.0.30", 4242))

        assert resolve_client_ip(scope) == "192.168.0.30", (
            "an unparsable header must be ignored, not trusted: accepting arbitrary text "
            "would let a caller mint unlimited rate-limit buckets and pollute GeoIP."
        )

    def test_ipv6_is_accepted(self) -> None:
        scope = _scope(headers=[(b"cf-connecting-ip", b"2001:db8::1")], client=("10.0.0.1", 1))

        assert resolve_client_ip(scope) == "2001:db8::1"


class TestTheResolverNeverBreaksARequest:
    """It runs in the middleware chain: a malformed scope degrades, never raises."""

    @pytest.mark.parametrize(
        "headers",
        [None, "not-a-list", 42, [("bad-shape",)], [None]],
        ids=["none", "string", "int", "short-tuple", "null-entry"],
    )
    def test_unusable_headers_degrade_to_the_peer(self, headers: object) -> None:
        scope = {"type": "http", "headers": headers, "client": ("192.168.0.30", 4242)}

        assert resolve_client_ip(scope) == "192.168.0.30"

    def test_a_request_like_object_without_a_real_scope_still_resolves(self) -> None:
        """Mirrors the loose doubles used by the auth contract tests."""

        class _RequestLike:
            scope = None
            client = type("Addr", (), {"host": "203.0.113.7"})()

        assert resolve_client_ip(_RequestLike()) == "203.0.113.7"
