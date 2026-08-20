"""Activity timeline router (Lot 1-A1) — auth binding and paging validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.session_dependencies import get_current_active_session
from src.domains.activity.router import router
from src.domains.activity.schemas import ActivityTimelineResponse

USER_ID = uuid.uuid4()


def _response(**overrides: object) -> ActivityTimelineResponse:
    base = ActivityTimelineResponse(
        events=[],
        totals=[],
        has_more=False,
        offset=0,
        limit=settings.activity_timeline_page_size,
        window_days=settings.activity_timeline_window_days,
    )
    return base.model_copy(update=dict(overrides))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    user = SimpleNamespace(id=USER_ID)
    app.dependency_overrides[get_current_active_session] = lambda: user
    return TestClient(app)


@pytest.mark.unit
class TestTimelineEndpoint:
    def test_returns_service_payload_for_authenticated_owner(self, client: TestClient):
        build = AsyncMock(return_value=_response())
        with patch("src.domains.activity.router.ActivityService") as service_cls:
            service_cls.return_value.build_timeline = build

            resp = client.get("/activity/timeline")

        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["window_days"] == settings.activity_timeline_window_days
        # The service is bound to the AUTHENTICATED user, never a query param.
        service_cls.assert_called_once_with(USER_ID)
        build.assert_awaited_once_with(offset=0, limit=settings.activity_timeline_page_size)

    def test_paging_params_flow_through(self, client: TestClient):
        build = AsyncMock(return_value=_response(offset=10, limit=5))
        with patch("src.domains.activity.router.ActivityService") as service_cls:
            service_cls.return_value.build_timeline = build

            resp = client.get("/activity/timeline?offset=10&limit=5")

        assert resp.status_code == 200
        build.assert_awaited_once_with(offset=10, limit=5)

    def test_negative_offset_is_rejected(self, client: TestClient):
        assert client.get("/activity/timeline?offset=-1").status_code == 422

    def test_limit_bounds_are_enforced(self, client: TestClient):
        assert client.get("/activity/timeline?limit=0").status_code == 422
        assert client.get("/activity/timeline?limit=101").status_code == 422

    def test_events_serialize_with_utc_timestamps(self, client: TestClient):
        from src.domains.activity.schemas import ActivityEvent

        event = ActivityEvent(
            kind="habit_detected",
            ref_id=str(uuid.uuid4()),
            occurred_at=datetime(2026, 8, 19, 10, 0, tzinfo=UTC),
            text="evening_review",
            status="active",
        )
        build = AsyncMock(return_value=_response(events=[event]))
        with patch("src.domains.activity.router.ActivityService") as service_cls:
            service_cls.return_value.build_timeline = build

            body = client.get("/activity/timeline").json()

        assert body["events"][0]["kind"] == "habit_detected"
        assert body["events"][0]["occurred_at"].startswith("2026-08-19T10:00:00")
