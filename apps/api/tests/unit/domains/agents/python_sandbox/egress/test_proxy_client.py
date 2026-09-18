"""The management client: reload with the bearer, and nothing succeeds by default."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from src.domains.agents.python_sandbox.egress.proxy_client import (
    EgressProxyUnavailable,
    ProxyManagement,
)

pytestmark = pytest.mark.unit


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> ProxyManagement:
    transport = httpx.MockTransport(handler)
    return ProxyManagement(
        management_url="http://egress:9093",
        health_url="http://egress:9094/healthz",
        token="tok-123",
        timeout_seconds=1,
        transport=transport,
    )


class TestReload:
    async def test_posts_the_bearer_and_accepts_ok(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("authorization", "")
            return httpx.Response(200, json={"status": "ok"})

        await _client(handler).reload()
        assert seen == {"path": "/v1/reload", "auth": "Bearer tok-123"}

    async def test_a_401_is_a_refusal_named_as_such(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Unauthorized")

        with pytest.raises(EgressProxyUnavailable, match="401"):
            await _client(handler).reload()

    async def test_a_connection_failure_is_a_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with pytest.raises(EgressProxyUnavailable, match="ConnectError"):
            await _client(handler).reload()


class TestHealth:
    async def test_ok_body_means_healthy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == httpx.URL("http://egress:9094/healthz")
            return httpx.Response(200, text="OK")

        assert await _client(handler).healthy() is True

    async def test_anything_else_is_not(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        assert await _client(handler).healthy() is False


class TestTokenFile:
    def test_the_token_is_read_stripped_from_the_config_volume(self, tmp_path: Path) -> None:
        (tmp_path / "management.token").write_text("abc123\n", encoding="utf-8")
        assert ProxyManagement.read_token(tmp_path) == "abc123"

    def test_a_missing_token_is_a_refusal(self, tmp_path: Path) -> None:
        with pytest.raises(EgressProxyUnavailable, match="management.token"):
            ProxyManagement.read_token(tmp_path)
