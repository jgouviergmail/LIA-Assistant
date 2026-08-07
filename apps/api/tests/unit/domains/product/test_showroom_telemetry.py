"""Credential-less showroom collector (P0 — public-web-showroom program).

What must hold:
- the showroom vocabulary is EXCLUSIVE: no overlap with the ordinary
  CLIENT_EVENT_TYPES / ANONYMOUS_EVENT_TYPES registries, so the ordinary
  /product/events schema keeps rejecting showroom names with 422 even for
  authenticated callers (funnel-pollution guard);
- POST /product/showroom-events has NO session dependency and NO Request
  parameter: rows always store user_id=NULL, run_id=NULL,
  channel="web_showroom", whatever cookies the browser sends;
- unknown, empty, or oversized batches are schema-rejected (422);
- the quota uses fixed GLOBAL Redis keys; quota exhaustion or Redis failure
  drops the batch with 202 (fail-closed measurement loss, never an
  IP-derived fallback, never a UX error).
"""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.domains.product.repository as repo_module
import src.domains.product.showroom_telemetry as showroom_module
import src.infrastructure.database as db_module
from src.domains.product.constants import (
    ANONYMOUS_EVENT_TYPES,
    CLIENT_EVENT_TYPES,
    PRODUCT_EVENT_DESCRIPTIONS,
    SHOWROOM_EVENT_TYPES,
    ProductEventType,
)
from src.domains.product.showroom_telemetry import (
    ingest_showroom_events,
    router,
)

#: Bounded mission ids — spelled out here on purpose (the oracle must not be
#: derived from the constant it checks).
EXPECTED_MISSION_IDS = {
    "overloaded_morning",
    "proactive_alert",
    "memory_dinner",
    "phone_booking",
    "daily_briefing",
    "config_tour",
}

EXPECTED_SHOWROOM = (
    {
        "demo_viewed",
        "demo_mission_started",
        "demo_first_hitl_decided",
        "demo_hitl_confirm",
        "demo_hitl_edit",
        "demo_hitl_cancel",
        "demo_completed",
        "demo_first_proof_opened",
        "demo_source_clicked",
        "demo_release_clicked",
        "demo_install_guide_clicked",
    }
    | {f"demo_mission_started_{m}" for m in EXPECTED_MISSION_IDS}
    | {f"demo_completed_{m}" for m in EXPECTED_MISSION_IDS}
)


class _StubRepo:
    events: list[dict[str, Any]] = []

    def __init__(self, db: Any) -> None:
        self.db = db

    async def record_event(self, **kwargs: Any) -> None:
        _StubRepo.events.append(kwargs)


class _AllowAllLimiter:
    async def acquire(self, **_: Any) -> bool:
        return True


class _DenyLimiter:
    async def acquire(self, **_: Any) -> bool:
        return False


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

    async def _get_limiter() -> _AllowAllLimiter:
        return _AllowAllLimiter()

    monkeypatch.setattr(showroom_module, "_get_rate_limiter", _get_limiter)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Vocabulary exclusivity
# ---------------------------------------------------------------------------


def test_showroom_vocabulary_is_exactly_the_program_funnel() -> None:
    assert {e.value for e in SHOWROOM_EVENT_TYPES} == EXPECTED_SHOWROOM


def test_mission_registry_matches_the_hand_spelled_oracle() -> None:
    from src.domains.product.constants import SHOWROOM_MISSION_IDS

    assert set(SHOWROOM_MISSION_IDS) == EXPECTED_MISSION_IDS
    # Every mission id carries BOTH per-mission events (started + completed) —
    # the frozenset derivation would raise at import otherwise; this spells
    # the contract out so a partial removal cannot slip through a refactor.
    values = {e.value for e in SHOWROOM_EVENT_TYPES}
    for mission in SHOWROOM_MISSION_IDS:
        assert f"demo_mission_started_{mission}" in values
        assert f"demo_completed_{mission}" in values


def test_showroom_vocabulary_never_overlaps_ordinary_registries() -> None:
    assert SHOWROOM_EVENT_TYPES & CLIENT_EVENT_TYPES == frozenset()
    assert SHOWROOM_EVENT_TYPES & ANONYMOUS_EVENT_TYPES == frozenset()


def test_every_showroom_event_is_described() -> None:
    for event in SHOWROOM_EVENT_TYPES:
        assert event in PRODUCT_EVENT_DESCRIPTIONS


def test_demo_started_stays_on_the_ordinary_legacy_path() -> None:
    # The legacy /demo branch keeps TrackView(demo_started) until retired.
    assert ProductEventType.DEMO_STARTED in CLIENT_EVENT_TYPES
    assert ProductEventType.DEMO_STARTED in ANONYMOUS_EVENT_TYPES
    assert ProductEventType.DEMO_STARTED not in SHOWROOM_EVENT_TYPES


# ---------------------------------------------------------------------------
# Route contract
# ---------------------------------------------------------------------------


def test_endpoint_has_no_session_or_request_parameter() -> None:
    params = inspect.signature(ingest_showroom_events).parameters
    names = " ".join(str(p) for p in params.values())
    assert "Request" not in names
    assert "session" not in names.lower()
    assert "user" not in names.lower()


def test_accepts_bounded_events_and_writes_null_identity(
    client: TestClient,
) -> None:
    client.cookies.set("lia_session", "should-be-ignored")
    resp = client.post(
        "/product/showroom-events",
        json={"events": ["demo_viewed", "demo_completed"]},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2, "dropped": 0}
    assert len(_StubRepo.events) == 2
    for row in _StubRepo.events:
        assert row["user_id"] is None
        assert row["run_id"] is None
        assert row["channel"] == "web_showroom"


@pytest.mark.parametrize(
    "payload",
    [
        {"events": ["totally_unknown"]},
        {"events": ["demo_started"]},  # ordinary vocabulary, not showroom
        {"events": ["landing_view"]},
        {"events": []},
        {"events": ["demo_viewed"] * 21},
        {"events": [{"kind": "event", "event_type": "demo_viewed"}]},
    ],
)
def test_unknown_or_free_form_is_422(client: TestClient, payload: dict) -> None:
    resp = client.post("/product/showroom-events", json=payload)
    assert resp.status_code == 422
    assert _StubRepo.events == []


def test_quota_exhaustion_drops_everything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _deny() -> _DenyLimiter:
        return _DenyLimiter()

    monkeypatch.setattr(showroom_module, "_get_rate_limiter", _deny)
    resp = client.post("/product/showroom-events", json={"events": ["demo_viewed"]})
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 0, "dropped": 1}
    assert _StubRepo.events == []


def test_redis_failure_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom() -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr(showroom_module, "_get_rate_limiter", _boom)
    resp = client.post("/product/showroom-events", json={"events": ["demo_viewed"]})
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 0, "dropped": 1}
    assert _StubRepo.events == []
