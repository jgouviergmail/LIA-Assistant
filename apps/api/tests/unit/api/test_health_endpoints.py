"""
Unit tests for the infrastructure probe endpoints (src/api/health.py).

Pins the liveness/readiness contract (ADR-115):

- ``GET /health`` is a **liveness** probe: HTTP 200 even when PostgreSQL or
  Redis are down — the payload degrades (``status: degraded``) but Docker
  must never restart the container for a dependency outage.
- ``GET /ready`` is a **readiness** probe: HTTP 200 only when both critical
  dependencies answer their probe, HTTP 503 otherwise.

Dependency probes are mocked at their lookup points
(``src.api.health.get_redis_cache`` and
``src.infrastructure.database.session.engine``) — no real services required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.health import health_router


def _make_client() -> TestClient:
    """Minimal app exposing only the probe router (no middleware stack)."""
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def _redis_up() -> AsyncMock:
    """``get_redis_cache`` replacement returning a client whose ping succeeds."""
    redis = MagicMock()
    redis.ping = AsyncMock()
    return AsyncMock(return_value=redis)


def _redis_down() -> AsyncMock:
    """``get_redis_cache`` replacement raising like an unreachable Redis."""
    return AsyncMock(side_effect=RuntimeError("redis unreachable"))


def _engine_up() -> MagicMock:
    """AsyncEngine stand-in whose ``connect()`` context manager succeeds."""
    engine = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
    return engine


def _engine_down() -> MagicMock:
    """AsyncEngine stand-in whose ``connect()`` raises like an unreachable DB."""
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("database unreachable")
    return engine


@pytest.mark.unit
class TestHealthLiveness:
    """GET /health — liveness: always 200, payload carries the degradation."""

    def test_returns_200_healthy_when_all_dependencies_up(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_up()),
            patch("src.infrastructure.database.session.engine", _engine_up()),
        ):
            response = _make_client().get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["checks"] == {"redis": "healthy", "database": "healthy"}
        assert "environment" in body

    def test_stays_200_degraded_when_redis_is_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_down()),
            patch("src.infrastructure.database.session.engine", _engine_up()),
        ):
            response = _make_client().get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"] == {"redis": "unhealthy", "database": "healthy"}

    def test_stays_200_degraded_when_database_is_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_up()),
            patch("src.infrastructure.database.session.engine", _engine_down()),
        ):
            response = _make_client().get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"] == {"redis": "healthy", "database": "unhealthy"}

    def test_stays_200_degraded_when_all_dependencies_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_down()),
            patch("src.infrastructure.database.session.engine", _engine_down()),
        ):
            response = _make_client().get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["checks"] == {"redis": "unhealthy", "database": "unhealthy"}


@pytest.mark.unit
class TestReadyReadiness:
    """GET /ready — readiness: 503 as soon as one critical dependency is down."""

    def test_returns_200_ready_when_all_dependencies_up(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_up()),
            patch("src.infrastructure.database.session.engine", _engine_up()),
        ):
            response = _make_client().get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"] == {"redis": "healthy", "database": "healthy"}

    def test_returns_503_when_redis_is_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_down()),
            patch("src.infrastructure.database.session.engine", _engine_up()),
        ):
            response = _make_client().get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"] == {"redis": "unhealthy", "database": "healthy"}

    def test_returns_503_when_database_is_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_up()),
            patch("src.infrastructure.database.session.engine", _engine_down()),
        ):
            response = _make_client().get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"] == {"redis": "healthy", "database": "unhealthy"}

    def test_returns_503_when_all_dependencies_down(self):
        with (
            patch("src.api.health.get_redis_cache", _redis_down()),
            patch("src.infrastructure.database.session.engine", _engine_down()),
        ):
            response = _make_client().get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"] == {"redis": "unhealthy", "database": "unhealthy"}
