"""Scan refusals must exclude normal session/resource errors and preserve HTTP contracts."""

import asyncio
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.core.middleware import setup_middleware


class _Guard:
    """External Redis boundary: recording any qualifying strike activates a ban."""

    def __init__(self) -> None:
        self.banned: set[str] = set()
        self.strikes: list[tuple[str, str, str]] = []

    async def remaining(self, client_ip: str) -> int:
        return 42 if client_ip in self.banned else 0

    async def record(self, client_ip: str, reason: str, fingerprint: str) -> bool:
        self.strikes.append((client_ip, reason, fingerprint))
        self.banned.add(client_ip)
        return True


@pytest.fixture
def guarded() -> Iterator[tuple[TestClient, _Guard]]:
    guard = _Guard()
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/records/{record_id}")
    async def missing_record(record_id: str) -> JSONResponse:
        return JSONResponse({"missing": record_id}, status_code=404)

    @app.get("/api/v1/auth/me")
    async def expired_session() -> JSONResponse:
        return JSONResponse({"error": "session_expired"}, status_code=401)

    @app.post("/api/v1/auth/login")
    async def invalid_credentials() -> JSONResponse:
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)

    @app.post("/api/v1/auth/mfa/verify")
    async def invalid_mfa() -> JSONResponse:
        return JSONResponse({"error": "invalid_code"}, status_code=401)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/body")
    async def body(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    with (
        patch("src.core.http_scan.RedisHTTPScanGuard", return_value=guard),
        patch("src.core.middleware.settings.rate_limit_enabled", False),
        patch("src.core.http_scan.settings.http_scan_protection_enabled", True),
        patch("src.core.middleware.settings.cors_origins", ["https://web.test"]),
    ):
        setup_middleware(app)
        with TestClient(app) as client:
            client.headers["CF-Connecting-IP"] = "8.8.8.8"
            yield client, guard


def test_unknown_404_bans_following_requests_with_cors_and_security_headers(guarded) -> None:
    client, guard = guarded
    assert client.get("/.env?token=secret").status_code == 404
    blocked = client.get("/ok", headers={"Origin": "https://web.test"})
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "http_scan_blocked"
    assert blocked.headers["retry-after"] == "42"
    assert blocked.headers["x-request-id"]
    assert blocked.headers["x-content-type-options"] == "nosniff"
    assert blocked.headers["access-control-allow-origin"] == "https://web.test"
    assert "retry-after" in blocked.headers["access-control-expose-headers"].lower()
    assert len(guard.strikes) == 1
    assert guard.strikes[0][0:2] == ("8.8.8.8", "not_found")
    assert "secret" not in guard.strikes[0][2]


@pytest.mark.parametrize("path", ["/records/absent", "/api/v1/auth/me"])
def test_resource_404_and_expired_session_never_ban(guarded, path: str) -> None:
    client, guard = guarded
    for _ in range(25):
        assert client.get(path).status_code in (401, 404)
    assert client.get("/ok").status_code == 200
    assert guard.strikes == []


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/mfa/verify"])
def test_credential_attempt_401_counts_and_other_ips_remain_admitted(guarded, path: str) -> None:
    client, guard = guarded
    assert client.post(path, json={}).status_code == 401
    assert client.get("/ok").status_code == 429
    assert client.get("/ok", headers={"CF-Connecting-IP": "1.1.1.1"}).status_code == 200
    assert guard.strikes[0][0:2] == ("8.8.8.8", "credentials")


def test_options_probes_and_internal_callers_are_never_banned(guarded) -> None:
    client, guard = guarded
    assert client.options("/unknown").status_code == 404
    assert client.get("/health").status_code == 200
    assert client.get("/unknown", headers={"CF-Connecting-IP": "127.0.0.1"}).status_code == 404
    assert client.get("/ok").status_code == 200
    assert guard.strikes == []


def test_xff_rotation_does_not_evade_ban_and_ipv6_is_canonical(guarded) -> None:
    client, _ = guarded
    assert client.get("/.git", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 404
    assert client.get("/ok", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    expanded = "2606:4700:4700:0000:0000:0000:0000:1111"
    assert client.get("/.env", headers={"CF-Connecting-IP": expanded}).status_code == 404
    assert (
        client.get("/ok", headers={"CF-Connecting-IP": "2606:4700:4700::1111"}).status_code == 429
    )


def test_disabled_protection_preserves_routing(guarded) -> None:
    client, guard = guarded
    with patch("src.core.http_scan.settings.http_scan_protection_enabled", False):
        assert client.get("/.env").status_code == 404
        assert client.get("/ok").status_code == 200
    assert guard.strikes == []


def test_unparseable_peer_or_forwarded_header_never_turns_into_a_500(guarded) -> None:
    client, guard = guarded
    client.headers.pop("CF-Connecting-IP")
    assert client.get("/.env").status_code == 404
    assert client.get("/ok", headers={"CF-Connecting-IP": "not-an-ip"}).status_code == 200
    assert guard.strikes == []


@pytest.mark.parametrize("operation", ["check", "record"])
async def test_slow_redis_fails_open_without_waiting_for_its_socket_timeout(operation: str) -> None:
    from src.infrastructure.observability.metrics_http_scan import http_scan_degraded_total
    from src.infrastructure.rate_limiting.http_scan import RedisHTTPScanGuard

    async def unavailable_cache():
        await asyncio.Event().wait()

    before = http_scan_degraded_total.labels(operation=operation)._value.get()
    with (
        patch("src.infrastructure.rate_limiting.http_scan.get_redis_cache", unavailable_cache),
        patch("src.core.config.settings.http_scan_redis_timeout_seconds", 0.01),
    ):
        async with asyncio.timeout(1):
            guard = RedisHTTPScanGuard()
            if operation == "check":
                assert await guard.remaining("8.8.8.8") == 0
            else:
                assert await guard.record("8.8.8.8", "not_found", "probe") is False
    assert http_scan_degraded_total.labels(operation=operation)._value.get() == before + 1
