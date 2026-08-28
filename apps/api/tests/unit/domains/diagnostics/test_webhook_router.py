"""Alertmanager webhook — Bearer-secret gated, idempotent, resolve-aware.

Security contract: the endpoint DOES NOT EXIST (404) while the feature flag is
off or the secret is unset; a wrong secret is 403 with a constant-time compare;
no alert content is logged above DEBUG.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from src.domains.diagnostics import webhook_router as webhook_module

_SECRET = "s3cret-long-enough"
_HEADER = {"Authorization": f"Bearer {_SECRET}"}


def _payload(status: str = "firing", alertname: str = "RedisDown") -> dict[str, Any]:
    return {
        "version": "4",
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": {"alertname": alertname, "severity": "critical", "component": "redis"},
                "annotations": {
                    "summary": "Redis is down",
                    "description": "redis-exporter unreachable",
                    "runbook": "docs/runbooks/alerts/RedisDown.md",
                },
                "fingerprint": "abc123",
                "startsAt": "2026-08-27T10:00:00Z",
            }
        ],
    }


class _FakeRepo:
    opened: list[dict[str, Any]] = []
    resolved: list[str] = []
    created_flag = True

    def __init__(self, db: Any) -> None:
        self.db = db

    async def open_or_touch_incident(self, **kwargs: Any) -> tuple[Any, bool, Any]:
        type(self).opened.append(kwargs)
        return uuid4(), type(self).created_flag, None

    async def resolve_incident(self, correlation_key: str, **_: Any) -> int:
        type(self).resolved.append(correlation_key)
        return 1


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    _FakeRepo.opened = []
    _FakeRepo.resolved = []
    _FakeRepo.created_flag = True
    monkeypatch.setattr(webhook_module.settings, "diagnostics_enabled", True)
    monkeypatch.setattr(webhook_module.settings, "diagnostics_webhook_secret", _SECRET)
    monkeypatch.setattr(webhook_module, "DiagnosticsRepository", _FakeRepo)

    @asynccontextmanager
    async def fake_db() -> Any:
        from unittest.mock import AsyncMock

        yield AsyncMock()

    monkeypatch.setattr(webhook_module, "get_db_context", fake_db)

    async def no_notify(**_: Any) -> int:
        return 0

    monkeypatch.setattr(webhook_module, "notify_admins_of_incident", no_notify)

    app = FastAPI()
    app.include_router(webhook_module.router)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


_URL = "/internal/diagnostics/alert-webhook"


@pytest.mark.unit
class TestWebhookSecurity:
    async def test_unset_secret_hides_the_endpoint(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(webhook_module.settings, "diagnostics_webhook_secret", "")
        response = await client.post(_URL, json=_payload(), headers=_HEADER)
        assert response.status_code == 404

    async def test_flag_off_hides_the_endpoint(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(webhook_module.settings, "diagnostics_enabled", False)
        response = await client.post(_URL, json=_payload(), headers=_HEADER)
        assert response.status_code == 404

    async def test_wrong_secret_is_denied(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            _URL, json=_payload(), headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 403
        assert _FakeRepo.opened == []

    async def test_missing_secret_header_is_denied(self, client: httpx.AsyncClient) -> None:
        response = await client.post(_URL, json=_payload())
        assert response.status_code == 403


@pytest.mark.unit
class TestWebhookBehaviour:
    async def test_firing_alert_opens_an_incident(self, client: httpx.AsyncClient) -> None:
        response = await client.post(_URL, json=_payload(), headers=_HEADER)
        assert response.status_code == 200
        assert response.json() == {"opened": 1, "resolved": 0}
        opened = _FakeRepo.opened[0]
        assert opened["correlation_key"] == "RedisDown"
        assert opened["source"] == "alert"
        assert opened["fingerprint"] == "abc123"
        assert opened["evidence"]["runbook"] == "docs/runbooks/alerts/RedisDown.md"

    async def test_resolved_alert_resolves_the_incident(self, client: httpx.AsyncClient) -> None:
        response = await client.post(_URL, json=_payload(status="resolved"), headers=_HEADER)
        assert response.status_code == 200
        assert response.json() == {"opened": 0, "resolved": 1}
        assert _FakeRepo.resolved == ["RedisDown"]

    async def test_alert_without_alertname_is_skipped_not_crashed(
        self, client: httpx.AsyncClient
    ) -> None:
        payload = _payload()
        payload["alerts"][0]["labels"].pop("alertname")
        response = await client.post(_URL, json=payload, headers=_HEADER)
        assert response.status_code == 200
        assert response.json() == {"opened": 0, "resolved": 0}

    async def test_malformed_payload_is_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(_URL, json={"nope": True}, headers=_HEADER)
        assert response.status_code == 422
