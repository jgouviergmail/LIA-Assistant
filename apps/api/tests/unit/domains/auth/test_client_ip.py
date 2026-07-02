"""Unit tests for auth client-IP extraction (rate-limit keying).

Proxy handling is delegated to uvicorn (``--proxy-headers``): the raw
X-Forwarded-For header must NOT be read here, otherwise any direct client
could forge it to rotate per-IP auth rate-limit keys.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from starlette.requests import Request

from src.domains.auth.dependencies import _get_client_ip


def _make_request(client_host: str | None, xff: str | None = None) -> Mock:
    request = Mock(spec=Request)
    request.client = SimpleNamespace(host=client_host) if client_host else None
    request.headers = {"X-Forwarded-For": xff} if xff else {}
    return request


class TestGetClientIp:
    """request.client.host is authoritative; raw XFF is never trusted."""

    def test_returns_client_host(self):
        assert _get_client_ip(_make_request("203.0.113.7")) == "203.0.113.7"

    def test_ignores_forged_x_forwarded_for(self):
        request = _make_request("192.168.0.50", xff="1.2.3.4")
        assert _get_client_ip(request) == "192.168.0.50"

    def test_no_client_returns_unknown(self):
        assert _get_client_ip(_make_request(None)) == "unknown"
