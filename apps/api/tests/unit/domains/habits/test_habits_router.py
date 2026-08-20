"""Habits control-surface endpoints (ADR-214) — ownership and honesty.

What must hold:
- the overview renders BEFORE the first nightly run (insufficient shape);
- every row-addressing endpoint is owner-scoped (foreign id → 404);
- the status transition and deletions commit and answer with live data;
- the preference toggle round-trips.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError
from src.core.session_dependencies import get_current_active_session
from src.domains.habits.router import router


class _StubRepo:
    """Repository double bound through HabitsService."""

    profile: Any = None
    habits: list[Any] = []
    activity_dates: list[Any] = []
    owned: Any = None
    deleted_all: int = 0
    rollup_wiped: bool = False

    def __init__(self, db: Any) -> None:
        self.db = db

    async def get_profile(self, user_id: uuid.UUID) -> Any:
        return _StubRepo.profile

    async def fetch_activity_dates(self, user_id: uuid.UUID) -> list[Any]:
        return list(_StubRepo.activity_dates)

    async def list_habits(self, user_id: uuid.UUID, kind: str | None = None) -> list[Any]:
        return list(_StubRepo.habits)

    async def get_owned(self, habit_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        return _StubRepo.owned

    async def set_status(self, habit: Any, status: str) -> None:
        habit.status = status

    async def delete_habit(self, habit: Any) -> None:
        _StubRepo.habits = [h for h in _StubRepo.habits if h is not habit]

    async def delete_all(self, user_id: uuid.UUID) -> int:
        return _StubRepo.deleted_all

    async def delete_profile(self, user_id: uuid.UUID) -> None:
        _StubRepo.profile = None

    async def delete_activity_rollup(self, user_id: uuid.UUID) -> None:
        _StubRepo.rollup_wiped = True


def _habit_row(status: str = "active") -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.kind = "active_window"
    row.key = "weekday:morning"
    row.payload = {"version": 1, "day_class": "weekday", "windows": []}
    row.status = status
    row.positive_signals = 2
    row.negative_signals = 0
    row.last_observed_at = datetime.now(UTC)
    row.created_at = datetime.now(UTC)
    return row


@pytest.fixture
def candidates_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Deterministic candidates source — unit tests never touch Redis."""
    import src.domains.habits.router as router_module

    mock = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(router_module, "list_recurrence_candidates", mock)
    return mock


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, candidates_mock: AsyncMock) -> TestClient:
    import src.domains.habits.service as service_module

    monkeypatch.setattr(service_module, "HabitsRepository", _StubRepo)
    _StubRepo.profile = None
    _StubRepo.habits = []
    _StubRepo.activity_dates = []
    _StubRepo.owned = None
    _StubRepo.deleted_all = 0
    _StubRepo.rollup_wiped = False

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    user = SimpleNamespace(id=uuid.uuid4(), habits_enabled=True)

    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(ResourceNotFoundError)
    async def _not_found(request: Any, exc: ResourceNotFoundError) -> Any:  # noqa: ANN401
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": "not found"})

    app.dependency_overrides[get_current_active_session] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_overview_renders_before_first_compute(client: TestClient) -> None:
    resp = client.get("/habits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["habits_enabled"] is True
    assert body["profile"]["computed_at"] is None
    assert body["profile"]["weekday"]["verdict"] == "insufficient"
    # The 24-bin distribution ships even pre-compute (all zeros) so the
    # heatmap consumer never needs a shape special-case.
    assert body["profile"]["weekday"]["bin_presence"] == [0.0] * 24
    assert body["habits"] == []


def test_overview_publishes_the_24_bin_distribution(client: TestClient) -> None:
    """The distribution-level profile reaches the panel: 'where' activity
    concentrates stays visible even when no window is claimable (the honest
    complement of a none/diffuse verdict)."""
    bins = [0.0] * 24
    bins[8], bins[9], bins[21] = 0.8, 0.5, 0.3
    profile_row = MagicMock()
    profile_row.computed_at = datetime.now(UTC)
    profile_row.payload = {
        "version": 1,
        "active_days_fraction": 0.7,
        "sparse": False,
        "classes": {
            "weekday": {
                "verdict": "none",
                "windows": [],
                "n_eff": 20.0,
                "bin_presence": bins,
            },
            "weekend": {
                "verdict": "none",
                "windows": [],
                "n_eff": 8.0,
                "bin_presence": [0.0] * 24,
            },
        },
    }
    _StubRepo.profile = profile_row
    resp = client.get("/habits")
    assert resp.status_code == 200
    weekday = resp.json()["profile"]["weekday"]
    assert len(weekday["bin_presence"]) == 24
    assert weekday["bin_presence"][8] == 0.8


def test_overview_lists_rows(client: TestClient) -> None:
    _StubRepo.habits = [_habit_row()]
    resp = client.get("/habits")
    assert resp.status_code == 200
    rows = resp.json()["habits"]
    assert len(rows) == 1
    assert rows[0]["key"] == "weekday:morning"
    assert rows[0]["status"] == "active"


def test_overview_publishes_observation_candidates(
    client: TestClient, candidates_mock: AsyncMock
) -> None:
    """Candidates ride the overview with the ENFORCED threshold published,
    every existing row key excluded (blocked tombstones must never resurface)
    and the display cap read from settings — never a re-declared number."""
    from src.core.config import settings as app_settings
    from src.domains.habits.candidates import RecurrenceCandidate

    _StubRepo.habits = [_habit_row()]
    candidates_mock.return_value = (
        [RecurrenceCandidate(key="email+contact", observed_days=3, required_days=4)],
        2,
    )
    resp = client.get("/habits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidates"] == [{"key": "email+contact", "observed_days": 3, "required_days": 4}]
    assert body["candidates_more"] == 2
    kwargs = candidates_mock.await_args.kwargs
    assert kwargs["exclude_keys"] == {"weekday:morning"}
    assert kwargs["limit"] == app_settings.habits_candidates_display_max


def test_explanation_of_a_recurring_habit_carries_real_observed_days(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Honest provenance: the ledger's REAL occurrence dates — the exact
    basis of the lock — never fabricated conversation references."""
    import src.domains.habits.router as router_module

    row = _habit_row()
    row.kind = "recurring_request"
    row.key = "email+contact"
    row.payload = {"version": 1, "shape": "weekly", "trigger_hour": 9.0, "days_of_week": [0]}
    _StubRepo.owned = row
    days_mock = AsyncMock(return_value=["2026-08-03", "2026-07-27", "2026-07-20"])
    monkeypatch.setattr(router_module, "observed_days_for_signature", days_mock)

    resp = client.get(f"/habits/{row.id}/explanation")
    assert resp.status_code == 200
    assert resp.json()["observed_days"] == ["2026-08-03", "2026-07-27", "2026-07-20"]
    assert days_mock.await_args.args[1] == "email+contact"


def test_explanation_of_a_window_habit_reads_no_ledger(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.habits.router as router_module

    row = _habit_row()  # kind=active_window
    _StubRepo.owned = row
    days_mock = AsyncMock(return_value=["2026-08-03"])
    monkeypatch.setattr(router_module, "observed_days_for_signature", days_mock)

    resp = client.get(f"/habits/{row.id}/explanation")
    assert resp.status_code == 200
    assert resp.json()["observed_days"] == []
    days_mock.assert_not_awaited()


def test_explanation_publishes_thresholds(client: TestClient) -> None:
    row = _habit_row()
    _StubRepo.owned = row
    resp = client.get(f"/habits/{row.id}/explanation")
    assert resp.status_code == 200
    thresholds = resp.json()["thresholds"]
    # The exact numbers the detector applied are published (ADR-184) —
    # values come from settings, so only presence of the keys is pinned.
    for key in ("presence_min", "wilson_floor", "capture_min", "selectivity_min"):
        assert key in thresholds


def test_explanation_thresholds_match_the_kind(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recurring habit was explained with the RHYTHM thresholds — numbers
    the lock evaluation never applies (ADR-184 violation surfaced by the
    provenance UI, code-review catch): each kind publishes ITS detector's
    thresholds, never the other's."""
    import src.domains.habits.router as router_module

    monkeypatch.setattr(router_module, "observed_days_for_signature", AsyncMock(return_value=[]))
    row = _habit_row()
    row.kind = "recurring_request"
    row.key = "email"
    _StubRepo.owned = row
    thresholds = client.get(f"/habits/{row.id}/explanation").json()["thresholds"]
    for key in ("min_distinct_days", "lock_r_min", "weekly_min_same_dow", "window_days"):
        assert key in thresholds
    assert "presence_min" not in thresholds  # rhythm numbers never leak here


def test_foreign_habit_is_404(client: TestClient) -> None:
    _StubRepo.owned = None
    assert client.get(f"/habits/{uuid.uuid4()}/explanation").status_code == 404
    assert (
        client.post(f"/habits/{uuid.uuid4()}/status", json={"status": "paused"}).status_code == 404
    )
    assert client.delete(f"/habits/{uuid.uuid4()}").status_code == 404


def test_block_transition_persists(client: TestClient) -> None:
    row = _habit_row()
    _StubRepo.owned = row
    resp = client.post(f"/habits/{row.id}/status", json={"status": "blocked"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"
    assert row.status == "blocked"


def test_invalid_status_rejected(client: TestClient) -> None:
    row = _habit_row()
    _StubRepo.owned = row
    resp = client.post(f"/habits/{row.id}/status", json={"status": "dormant"})
    assert resp.status_code == 422


def test_delete_all_wipes_rows_and_profile(client: TestClient) -> None:
    _StubRepo.deleted_all = 3
    resp = client.delete("/habits")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted_habits"] == 3
    assert body["profile_deleted"] is True
    # The durable rollup is wiped too — otherwise a recompute would resurrect
    # the profile from data the user just asked to forget.
    assert _StubRepo.rollup_wiped is True


def test_settings_toggle_round_trips(client: TestClient) -> None:
    resp = client.patch("/habits/settings", json={"habits_enabled": False})
    assert resp.status_code == 200
    assert resp.json() == {"habits_enabled": False}


def test_recompute_now_returns_fresh_profile(client: TestClient) -> None:
    """Manual recompute (ADR-214 review follow-up): the nightly aggregation is
    retroactive by construction (56-day window), so a user activating the
    feature — or resetting it — must not wait a night to see their profile.
    The endpoint runs the SAME unit of work as the job and answers with the
    fresh overview shape."""
    profile_row = MagicMock()
    profile_row.payload = {
        "version": 1,
        "active_days_fraction": 0.8,
        "sparse": False,
        "classes": {
            "weekday": {
                "verdict": "windows",
                "windows": [{"start_hour": 8, "end_hour": 10, "presence": 0.9}],
                "n_eff": 20.0,
                "bin_presence": [0.0] * 24,
            },
            "weekend": {
                "verdict": "none",
                "windows": [],
                "n_eff": 8.0,
                "bin_presence": [0.0] * 24,
            },
        },
    }
    profile_row.computed_at = datetime.now(UTC)

    recomputed: list[str] = []

    async def _fake_recompute(self: Any, user: Any, force: bool = False) -> str:
        # The manual endpoint must force: an explicit user action can never
        # be swallowed by the delta-skip (live-proof catch 2026-08-05).
        assert force is True
        recomputed.append("yes")
        _StubRepo.profile = profile_row
        return "computed"

    from src.domains.habits.service import HabitsService

    original = HabitsService.recompute_user_profile
    HabitsService.recompute_user_profile = _fake_recompute  # type: ignore[method-assign]
    try:
        resp = client.post("/habits/recompute")
    finally:
        HabitsService.recompute_user_profile = original  # type: ignore[method-assign]

    assert resp.status_code == 200
    assert recomputed == ["yes"]
    body = resp.json()
    assert body["profile"]["weekday"]["verdict"] == "windows"
    assert body["outcome"] == "computed"


def test_insufficient_verdict_publishes_the_unlock_threshold(client: TestClient) -> None:
    """ADR-184: the enforced bound (effective days before claims) is published
    with the observed count, so the settings surface can show a progress bar
    instead of an unquantified 'still learning' frustration."""
    resp = client.get("/habits")
    body = resp.json()
    assert body["profile"]["weekday"]["n_eff"] == 0.0
    assert body["profile"]["weekday"]["required_n_eff"] > 0
    assert body["profile"]["weekend"]["required_n_eff"] > 0


def test_overview_carries_the_streak_block(client: TestClient) -> None:
    """The ledger's streak facts reach the panel (Lot 1-A4): current and
    longest runs plus the settings-driven milestone positions."""
    from datetime import date, timedelta

    from src.core.config import settings

    today = date.today()
    _StubRepo.activity_dates = [today - timedelta(days=offset) for offset in range(3)]

    body = client.get("/habits").json()

    assert body["streak"]["current"] >= 3
    assert body["streak"]["longest"] >= 3
    assert body["streak"]["next_milestone"] == min(settings.habits_streak_milestones)
    assert body["streak"]["milestone_reached"] is None
