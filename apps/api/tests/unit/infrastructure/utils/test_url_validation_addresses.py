"""A pinned fetch keeps the resolver's order and survives an unreachable address.

ADR-326 pins a validated URL on an address its check saw. Measured on production
on 2026-10-13: the API container has no IPv6 route, the system resolver lists
IPv4 first, and ``_resolve_dns_sync`` collected the addresses in a ``set`` — so
a worker whose hash seed put the IPv6 address first failed every fetch of that
host with ``ConnectError`` while a by-name connection succeeded. These tests
pin the two halves of the repair: the resolver's order is the order tried, and
a connection that cannot be established moves to the next VALIDATED address.
"""

import socket

import httpx
import pytest

from src.infrastructure.utils.url_validation import (
    UrlValidationResult,
    _resolve_dns_sync,
    pinned_request_parts,
    pinned_stream,
)

V4 = "93.184.216.34"
V4_B = "93.184.216.35"
V6 = "2606:2800:220:1:248:1893:25c8:1946"


def _addrinfo(*addresses: str) -> list[tuple[object, ...]]:
    """What ``socket.getaddrinfo`` returns for these addresses, in this order."""
    rows: list[tuple[object, ...]] = []
    for address in addresses:
        if ":" in address:
            rows.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, 0, 0, 0)))
        else:
            rows.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)))
    return rows


def _verdict(*addresses: str) -> UrlValidationResult:
    return UrlValidationResult(
        valid=True, url="https://example.com/page", resolved_ips=tuple(addresses)
    )


class TestResolverOrder:
    """The system resolver sorts its answer (RFC 6724); that order is the one tried."""

    # Two orders of the SAME addresses: an unordered collection answers both
    # identically, so it fails one of the two cases whatever the hash seed.
    @pytest.mark.parametrize(
        ("answer", "expected"),
        [
            ((V4, V6, V4, V4_B), [V4, V6, V4_B]),
            ((V6, V4_B, V6, V4), [V6, V4_B, V4]),
        ],
        ids=["ipv4 first", "ipv6 first"],
    )
    def test_the_resolver_order_is_kept_and_repeats_dropped(
        self, monkeypatch: pytest.MonkeyPatch, answer: tuple[str, ...], expected: list[str]
    ) -> None:
        monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _addrinfo(*answer))
        assert _resolve_dns_sync("example.com") == expected


class TestUnreachableAddress:
    """A connection that cannot be established moves to the next validated address."""

    async def test_a_refused_connection_moves_to_the_next_validated_address(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.host == V6:
                raise httpx.ConnectError("[Errno 101] Network is unreachable", request=request)
            return httpx.Response(200, content=b"ok")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async with pinned_stream(client, "GET", _verdict(V6, V4)) as response:
                assert response.status_code == 200
                assert await response.aread() == b"ok"

        assert [request.url.host for request in seen] == [V6, V4]
        for request in seen:
            # The name travels unchanged on every attempt: Host and SNI.
            assert request.headers["host"] == "example.com"
            assert request.extensions["sni_hostname"] == "example.com"

    async def test_when_every_address_refuses_the_last_refusal_is_raised(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            raise httpx.ConnectError(f"refused by {request.url.host}", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ConnectError, match=f"refused by {V4}"):
                async with pinned_stream(client, "GET", _verdict(V6, V4)):
                    pytest.fail("no address answered, the body must not run")
        assert seen == [V6, V4]

    async def test_a_timeout_is_not_retried_on_another_address(self) -> None:
        # Bounded time: a timeout already spent the request's budget.
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            raise httpx.ConnectTimeout("timed out", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ConnectTimeout):
                async with pinned_stream(client, "GET", _verdict(V6, V4)):
                    pytest.fail("the body must not run")
        assert seen == [V6]

    async def test_an_answer_is_never_retried_even_a_server_error(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async with pinned_stream(client, "GET", _verdict(V6, V4)) as response:
                assert response.status_code == 503
        assert seen == [V6]

    async def test_an_error_raised_by_the_caller_is_not_a_connection_failure(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            return httpx.Response(200, content=b"ok")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RuntimeError, match="caller"):
                async with pinned_stream(client, "GET", _verdict(V6, V4)):
                    raise RuntimeError("caller")
        assert seen == [V6]


class TestOnlyValidatedAddresses:
    """No attempt may leave the set the check saw (ADR-326's SSRF guarantee)."""

    def test_an_address_the_verdict_did_not_validate_is_refused(self) -> None:
        with pytest.raises(ValueError, match="validated"):
            pinned_request_parts(_verdict(V4), address="10.0.0.1")

    def test_a_named_validated_address_is_the_one_pinned(self) -> None:
        url, headers, _extensions = pinned_request_parts(_verdict(V6, V4), address=V4)
        assert url.host == V4
        assert headers == {"Host": "example.com"}
