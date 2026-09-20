"""Where the vendor calls back, and whether it can (ADR-301)."""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.telephony.callback import (
    CALLBACK_NOT_PUBLIC,
    callback_base_url,
    is_public_host,
    live_unavailable_reason,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "LOCALHOST",
        "127.0.0.1",
        "::1",
        "[::1]",
        "10.0.0.4",
        "172.20.1.9",
        "192.168.1.20",
        "169.254.1.1",
        "0.0.0.0",
        "host.docker.internal",
        "api",
        "lia.local",
        "box.lan",
        "svc.internal",
        "",
        # Wildcard DNS names embed the address they resolve to: a private one
        # is still private (the dev instance's own API_URL, measured 2026-09-20).
        "192.168.1.20.nip.io",
        "api.192.168.1.20.nip.io",
        "192-168-1-20.nip.io",
        "lia-10-0-0-4.sslip.io",
        "127.0.0.1.traefik.me",
    ],
)
def test_private_hosts_are_never_reachable_by_the_vendor(host: str) -> None:
    assert is_public_host(host) is False


@pytest.mark.parametrize(
    "host",
    [
        "lia-back.example.com",
        "8.8.8.8",
        "2606:4700::1111",
        "tunnel.trycloudflare.com",
        # A wildcard DNS name embedding a GLOBAL address is reachable.
        "8.8.8.8.nip.io",
        "app-8-8-8-8.sslip.io",
        # Digits in a name are not an address.
        "v2.example.com",
        "lia-2026-09-20.example.com",
    ],
)
def test_public_hosts_are(host: str) -> None:
    assert is_public_host(host) is True


def test_the_declared_base_wins_and_loses_its_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_url", "https://localhost:8000", raising=False)
    monkeypatch.setattr(
        settings, "telephony_callback_base_url", "https://tunnel.example.org/", raising=False
    )
    assert callback_base_url() == "https://tunnel.example.org"
    assert live_unavailable_reason() is None
    monkeypatch.setattr(settings, "telephony_callback_base_url", "  ", raising=False)
    assert callback_base_url() == "https://localhost:8000"
    assert live_unavailable_reason() == CALLBACK_NOT_PUBLIC
