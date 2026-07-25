"""HTTP rate limiting — the global limit is actually enforced (SEC-016).

A ``slowapi.Limiter`` was built with ``default_limits`` and parked on
``app.state``, but nothing ever consulted it: no ``SlowAPIMiddleware``, no
``@limiter.limit`` decorator. The API advertised a limit it did not apply, and
this very file asserted the illusion — it tested the 429 handler in isolation
and ended its "enforcement" test on a bare ``pass``.

``RateLimitMiddleware`` replaces it: Redis-backed (shared across the four
uvicorn workers, unlike SlowAPI's in-memory default), keyed on the client
address, fail-open when Redis is down, and on the request path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.constants import RATE_LIMIT_GLOBAL_EXEMPT_PATHS
from src.core.middleware import RateLimitMiddleware
from src.main import app

# ============================================================================
# Rate Limit Configuration Tests
# ============================================================================


def test_rate_limit_config_rate_limiting_enabled():
    """Test that rate_limiting_enabled reads from settings."""
    from src.core.rate_limit_config import rate_limiting_enabled

    # Test enabled
    settings_enabled = Settings(rate_limit_enabled=True)
    assert rate_limiting_enabled(settings_enabled) is True

    # Test disabled
    settings_disabled = Settings(rate_limit_enabled=False)
    assert rate_limiting_enabled(settings_disabled) is False


# ============================================================================
# Integration Tests (require full app context)
# ============================================================================


def test_slowapi_limiter_is_gone():
    """SEC-016: the unenforced SlowAPI limiter must not come back.

    `app.state.limiter` and the `RateLimitExceeded` handler used to exist while
    NOTHING consulted them — no middleware, no decorator. The API looked
    rate-limited and was not. Restoring that object without wiring it would
    recreate exactly the illusion this finding is about.
    """
    assert not hasattr(app.state, "limiter"), (
        "app.state.limiter is back — if SlowAPI is reintroduced it must be "
        "enforced (SlowAPIMiddleware or @limiter.limit), not merely declared."
    )


def test_global_rate_limit_middleware_is_installed():
    """The replacement control is actually on the request path."""
    from src.core.middleware import RateLimitMiddleware

    installed = [m.cls for m in app.user_middleware]
    assert RateLimitMiddleware in installed, (
        "RateLimitMiddleware must be installed — a limit that no middleware "
        "applies is the defect SEC-016 describes."
    )


def test_rate_limit_runs_before_the_body_is_read():
    """A client over budget is refused before we spend memory on its body.

    Ordering is the whole point: rejecting after buffering up to 21 MB would
    make the cheap refusal the expensive one.
    """
    from src.core.middleware import BodySizeLimitMiddleware, RateLimitMiddleware

    order = [m.cls for m in app.user_middleware]
    assert order.index(RateLimitMiddleware) < order.index(BodySizeLimitMiddleware)


def test_health_endpoint_returns_200():
    """Test that the health endpoint routes and serializes (baseline test).

    The dependency probes are mocked so this unit test opens NO real loopback
    DB/Redis connection: a bare ``TestClient(app)`` never runs the app lifespan
    shutdown, so a real ``engine.connect()`` / ``get_redis_cache()`` would leave
    a connection pooled on a dead portal loop, surfacing as an unclosed-socket
    ``PytestUnraisableExceptionWarning`` (now a hard error). Mocking keeps the
    smoke deterministic (always 200) and hermetic; the real probe behaviour is
    covered by tests/unit/api/test_health_endpoints.py against a minimal app.
    """
    redis_ok = AsyncMock(return_value=MagicMock(ping=AsyncMock()))

    engine_ok = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    engine_ok.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine_ok.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.api.health.get_redis_cache", redis_ok),
        patch("src.infrastructure.database.session.engine", engine_ok),
    ):
        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 200


def test_root_endpoint_returns_200():
    """Test that root endpoint works (baseline test)."""
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "LIA API"


# ============================================================================
# RateLimitMiddleware behaviour (SEC-016)
# ============================================================================


def _make_client(*, allowed: bool | Exception, monkeypatch, max_calls: int = 5) -> TestClient:
    """Build a minimal app carrying only the middleware under test.

    Args:
        allowed: Verdict the Redis limiter returns, or an exception it raises.
        monkeypatch: pytest fixture.
        max_calls: Ceiling advertised to the middleware.

    Returns:
        TestClient over an app with one echo route.
    """
    monkeypatch.setattr(
        "src.core.middleware.settings.rate_limit_global_per_minute", max_calls, raising=False
    )
    monkeypatch.setattr("src.core.middleware.rate_limiting_enabled", lambda _s: True)

    limiter = MagicMock()
    if isinstance(allowed, Exception):
        limiter.acquire = AsyncMock(side_effect=allowed)
    else:
        limiter.acquire = AsyncMock(return_value=allowed)
    monkeypatch.setattr("src.core.middleware.get_rate_limiter", AsyncMock(return_value=limiter))

    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware)

    @test_app.get("/api/v1/thing")
    async def thing() -> dict[str, bool]:
        return {"ok": True}

    @test_app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(test_app)
    client.limiter = limiter  # type: ignore[attr-defined]
    return client


class TestGlobalLimitEnforcement:
    """A request over budget is actually refused."""

    def test_allowed_request_reaches_the_route(self, monkeypatch):
        """Within budget, nothing changes for the caller."""
        client = _make_client(allowed=True, monkeypatch=monkeypatch)

        response = client.get("/api/v1/thing")

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_over_budget_request_is_refused(self, monkeypatch):
        """Over budget, the route is never reached.

        The old test made 70 requests and ended on `pass` — it could not have
        failed. This one asserts the status AND that the handler did not run.
        """
        client = _make_client(allowed=False, monkeypatch=monkeypatch)

        response = client.get("/api/v1/thing")

        assert response.status_code == 429
        assert "ok" not in response.json()

    def test_refusal_carries_the_retry_contract(self, monkeypatch):
        """The client is told when to come back, in header and body."""
        client = _make_client(allowed=False, monkeypatch=monkeypatch)

        response = client.get("/api/v1/thing")

        assert response.headers["Retry-After"] == "60"
        body = response.json()
        assert body["error"] == "rate_limit_exceeded"
        assert body["retry_after"] == 60

    def test_configured_ceiling_is_the_one_applied(self, monkeypatch):
        """The limiter is called with the configured budget, not a hardcoded one."""
        client = _make_client(allowed=True, monkeypatch=monkeypatch, max_calls=123)

        client.get("/api/v1/thing")

        kwargs = client.limiter.acquire.await_args.kwargs
        assert kwargs["max_calls"] == 123
        assert kwargs["window_seconds"] == 60


class TestRedisUnavailable:
    """The documented fail-open policy, and its visibility."""

    def test_request_is_admitted_when_redis_fails(self, monkeypatch):
        """A Redis outage must not become an API outage.

        Single-instance deployment: failing closed would turn a cache incident
        into total unavailability — worse than the abuse the limit prevents.
        Consistent with every other limiter in this codebase.
        """
        client = _make_client(allowed=ConnectionError("redis down"), monkeypatch=monkeypatch)

        response = client.get("/api/v1/thing")

        assert response.status_code == 200

    def test_degraded_window_is_counted(self, monkeypatch):
        """Fail-open is only acceptable if it is measurable."""
        from src.infrastructure.observability.metrics import http_rate_limit_degraded_total

        before = http_rate_limit_degraded_total._value.get()
        client = _make_client(allowed=RuntimeError("boom"), monkeypatch=monkeypatch)

        client.get("/api/v1/thing")

        assert http_rate_limit_degraded_total._value.get() == before + 1


class TestExemptionsAndScope:
    """What the limit must never break."""

    def test_health_probe_is_exempt(self, monkeypatch):
        """Docker's healthcheck and Prometheus must not rate-limit supervision."""
        client = _make_client(allowed=False, monkeypatch=monkeypatch)

        response = client.get("/health")

        assert response.status_code == 200
        client.limiter.acquire.assert_not_awaited()

    def test_every_declared_probe_path_is_exempt(self):
        """The exemption list covers the probes the platform actually polls."""
        assert "/health" in RATE_LIMIT_GLOBAL_EXEMPT_PATHS
        assert "/ready" in RATE_LIMIT_GLOBAL_EXEMPT_PATHS
        assert "/metrics" in RATE_LIMIT_GLOBAL_EXEMPT_PATHS

    def test_disabled_setting_skips_the_check(self, monkeypatch):
        """RATE_LIMIT_ENABLED=false must bypass the limiter entirely."""
        client = _make_client(allowed=False, monkeypatch=monkeypatch)
        monkeypatch.setattr("src.core.middleware.rate_limiting_enabled", lambda _s: False)

        response = client.get("/api/v1/thing")

        assert response.status_code == 200
        client.limiter.acquire.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_websocket_scope_is_not_intercepted(self, monkeypatch):
        """WebSockets have their own admission (single-use ticket + connection cap).

        Charging frames against an HTTP-per-minute budget would drop the voice
        transcription socket mid-session.
        """
        seen: dict[str, object] = {}

        async def downstream(scope, receive, send):
            seen["type"] = scope["type"]

        middleware = RateLimitMiddleware(downstream)

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            return None

        await middleware({"type": "websocket", "path": "/ws/audio"}, receive, send)

        assert seen["type"] == "websocket"


class TestClientKeying:
    """One budget per client, not one shared bucket."""

    def test_key_is_derived_from_the_peer_address(self, monkeypatch):
        """Distinct clients get distinct buckets."""
        client = _make_client(allowed=True, monkeypatch=monkeypatch)

        client.get("/api/v1/thing")

        key = client.limiter.acquire.await_args.kwargs["key"]
        assert key.startswith("http:global:")

    def test_key_ignores_a_forged_forwarded_header(self, monkeypatch):
        """X-Forwarded-For is NOT read here — uvicorn already resolved the peer.

        Reading the raw header would let any direct caller mint a fresh budget
        per request by rotating the value, defeating the limit entirely.
        """
        client = _make_client(allowed=True, monkeypatch=monkeypatch)

        client.get("/api/v1/thing", headers={"X-Forwarded-For": "1.2.3.4"})
        forged_key = client.limiter.acquire.await_args.kwargs["key"]

        client.get("/api/v1/thing", headers={"X-Forwarded-For": "5.6.7.8"})
        other_key = client.limiter.acquire.await_args.kwargs["key"]

        assert forged_key == other_key, "a spoofed header must not change the bucket"
