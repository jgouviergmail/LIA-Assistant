"""Telemetry ingestion endpoint (ADR-178 Phase 4) — bounded and fail-silent.

What must hold:
- anonymous callers: pre-signup funnel accepted, session-only events DROPPED
  silently (never an error — telemetry must not degrade the UX);
- authenticated callers: full client-event set accepted;
- search/vitals route to their bounded Prometheus families (seconds vs ratio);
- out-of-vocabulary values and oversized batches are schema-rejected (422).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.domains.product.repository as repo_module
import src.infrastructure.database as db_module
from src.core.session_dependencies import get_optional_session
from src.domains.product.router import _rate_limit_product_events, router
from src.domains.product.schemas import MAX_EVENTS_PER_BATCH


class _StubRepo:
    events: list[dict[str, Any]] = []

    def __init__(self, db: Any) -> None:
        self.db = db

    async def record_event(self, **kwargs: Any) -> None:
        _StubRepo.events.append(kwargs)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _fake_ctx():  # noqa: ANN202
        yield session

    monkeypatch.setattr(db_module, "get_db_context", _fake_ctx)
    monkeypatch.setattr(repo_module, "ProductRepository", _StubRepo)
    _StubRepo.events = []

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_rate_limit_product_events] = lambda: None
    app.dependency_overrides[get_optional_session] = lambda: None
    return TestClient(app)


def _authed(client: TestClient) -> TestClient:
    user = SimpleNamespace(id=uuid4())
    client.app.dependency_overrides[get_optional_session] = lambda: user  # type: ignore[union-attr]
    return client


def test_anonymous_funnel_accepted_session_events_dropped(client: TestClient) -> None:
    resp = client.post(
        "/product/events",
        json={
            "events": [
                {"kind": "event", "event_type": "landing_view"},
                {"kind": "event", "event_type": "demo_completed"},
                {"kind": "event", "event_type": "pwa_installed"},  # session-only
            ]
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2, "dropped": 1}
    assert [e["event_type"].value for e in _StubRepo.events] == [
        "landing_view",
        "demo_completed",
    ]
    assert all(e["user_id"] is None for e in _StubRepo.events)


def test_authenticated_full_set_accepted(client: TestClient) -> None:
    resp = _authed(client).post(
        "/product/events",
        json={"events": [{"kind": "event", "event_type": "pwa_installed"}]},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1, "dropped": 0}
    assert _StubRepo.events[0]["user_id"] is not None


def test_search_and_vitals_hit_bounded_families(client: TestClient) -> None:
    from src.infrastructure.observability.metrics_product import (
        product_search_total,
        product_web_vital_ratio,
        product_web_vital_seconds,
    )

    search_before = product_search_total.labels(
        surface="settings", outcome="zero_results", device_class="unknown"
    )._value.get()
    lcp_before = product_web_vital_seconds.labels(metric="lcp", device_class="unknown")._sum.get()
    cls_before = product_web_vital_ratio.labels(metric="cls", device_class="unknown")._sum.get()

    resp = client.post(
        "/product/events",
        json={
            "events": [
                {"kind": "search", "surface": "settings", "outcome": "zero_results"},
                {"kind": "vital", "metric": "lcp", "value": 2.5},
                {"kind": "vital", "metric": "cls", "value": 0.07},
                {"kind": "vital", "metric": "lcp"},  # incomplete -> dropped
            ]
        },
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 3, "dropped": 1}
    assert (
        product_search_total.labels(
            surface="settings", outcome="zero_results", device_class="unknown"
        )._value.get()
        == search_before + 1
    )
    assert product_web_vital_seconds.labels(
        metric="lcp", device_class="unknown"
    )._sum.get() == pytest.approx(lcp_before + 2.5)
    assert product_web_vital_ratio.labels(
        metric="cls", device_class="unknown"
    )._sum.get() == pytest.approx(cls_before + 0.07)
    assert _StubRepo.events == []  # search/vitals never touch the database


@pytest.mark.parametrize(
    "bad_item",
    [
        {"kind": "event", "event_type": "totally_unknown"},
        {"kind": "search", "surface": "cli", "outcome": "results"},
        {"kind": "vital", "metric": "fid", "value": 1.0},
        {"kind": "vital", "metric": "lcp", "value": 999.0},
    ],
)
def test_out_of_vocabulary_rejected(client: TestClient, bad_item: dict) -> None:
    resp = client.post("/product/events", json={"events": [bad_item]})
    assert resp.status_code == 422


def test_batch_size_capped(client: TestClient) -> None:
    events = [{"kind": "event", "event_type": "landing_view"}] * (MAX_EVENTS_PER_BATCH + 1)
    resp = client.post("/product/events", json={"events": events})
    assert resp.status_code == 422
