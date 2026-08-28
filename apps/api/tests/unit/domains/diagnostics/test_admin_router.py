"""Admin diagnostics REST — superuser-only, exact totals, briefing-style.

The overview is COMPOSED ONCE in the service layer and shared verbatim with
the platform_health chat tool (factorisation contract under test).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.diagnostics import router as admin_router_module
from src.domains.diagnostics import service as service_module


def _app(is_superuser: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router_module.router)
    user = MagicMock()
    user.id = uuid4()
    user.is_superuser = is_superuser

    async def fake_user() -> Any:
        return user

    async def fake_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_active_session] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _client(is_superuser: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(is_superuser))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def incidents(monkeypatch: pytest.MonkeyPatch) -> list[MagicMock]:
    incident = MagicMock()
    incident.id = uuid4()
    incident.correlation_key = "RedisDown"
    incident.source = "alert"
    incident.severity = "critical"
    incident.status = "open"
    incident.title = "Redis is down"
    incident.opened_at = datetime.now(UTC)
    incident.last_seen_at = datetime.now(UTC)
    incident.resolved_at = None
    incident.diagnosis = {"diagnosis": "d"}
    incident.evidence = {"summary": "s"}
    incident.action_log = []

    class _Repo:
        def __init__(self, db: Any) -> None: ...

        async def list_incidents(self, **kwargs: Any) -> tuple[list[Any], int]:
            return [incident], 42

        async def get_incident(self, incident_id: Any) -> Any:
            return incident if incident_id == incident.id else None

        async def latest_snapshot(self) -> Any:
            return None

        async def snapshots_since(self, since: Any, limit: int = 500) -> list[Any]:
            return []

    monkeypatch.setattr(admin_router_module, "DiagnosticsRepository", _Repo)
    monkeypatch.setattr(service_module, "DiagnosticsRepository", _Repo)
    return [incident]


@pytest.mark.unit
class TestAuthz:
    @pytest.mark.parametrize(
        "path",
        [
            "/admin/diagnostics/overview",
            "/admin/diagnostics/incidents",
            "/admin/diagnostics/snapshots",
        ],
    )
    async def test_non_superuser_is_403(
        self, path: str, incidents: list[MagicMock], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def empty_overview(db: Any) -> dict[str, Any]:
            return {}

        monkeypatch.setattr(admin_router_module, "build_overview", empty_overview)
        async with _client(is_superuser=False) as client:
            response = await client.get(path)
        assert response.status_code == 403


@pytest.mark.unit
class TestIncidentEndpoints:
    async def test_list_returns_exact_total(self, incidents: list[MagicMock]) -> None:
        async with _client() as client:
            response = await client.get("/admin/diagnostics/incidents")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 42  # COUNT(*), never the page length
        assert body["items"][0]["correlation_key"] == "RedisDown"
        assert body["items"][0]["has_diagnosis"] is True

    async def test_detail_found_and_not_found(self, incidents: list[MagicMock]) -> None:
        async with _client() as client:
            ok = await client.get(f"/admin/diagnostics/incidents/{incidents[0].id}")
            missing = await client.get(f"/admin/diagnostics/incidents/{uuid4()}")
        assert ok.status_code == 200
        assert ok.json()["diagnosis"] == {"diagnosis": "d"}
        assert missing.status_code == 404


@pytest.mark.unit
class TestOverview:
    async def test_overview_delegates_to_the_shared_service(
        self, incidents: list[MagicMock], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_overview(db: Any) -> dict[str, Any]:
            return {"snapshot_available": False, "open_incidents": 42}

        monkeypatch.setattr(admin_router_module, "build_overview", fake_overview)
        async with _client() as client:
            response = await client.get("/admin/diagnostics/overview")
        assert response.status_code == 200
        assert response.json()["open_incidents"] == 42

    def test_chat_tool_reuses_the_same_service_function(self) -> None:
        """Factorisation contract: one overview implementation, two surfaces."""
        import inspect

        from src.domains.agents.tools import diagnostics_tools

        assert "build_overview" in inspect.getsource(
            diagnostics_tools.platform_health_tool.coroutine
        )
