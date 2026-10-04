"""Every image the media proxies serve is counted where Google bills it.

The route map used to be PRE-COUNTED by the tool that built its URL (a fetch
that may never happen, and a re-fetch past the browser cache never counted),
the location map was never counted at all, and neither proxy held a tracker.
Now one helper fetches, counts on the 200 and persists under the accounting
the signed URL names — the four proxies (routes map, location map, Street
View, Places photo) all go through it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
from src.core.context import current_tracker
from src.core.dependencies import get_db
from src.core.exceptions import ExternalServiceError, UsageLimitExceededError, ValidationError
from src.core.session_dependencies import get_current_active_session
from src.domains.chat.service import TrackingContext
from src.domains.connectors import media_proxy_router as mod
from src.domains.connectors import router as routes
from src.domains.connectors.media_attribution import with_attribution
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitCheckResult, UsageLimitService
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def usage_check(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Every provider fetch is hermetic, including its spending decision."""
    checker = AsyncMock(return_value=UsageLimitCheckResult(True, UsageLimitStatus.OK, None, None))
    monkeypatch.setattr(UsageLimitService, "check_user_allowed", checker)
    return checker


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch) -> list[TrackingContext]:
    """Capture every tracker the helper persists, without a database."""
    seen: list[TrackingContext] = []

    async def _persist(self: TrackingContext) -> None:
        seen.append(self)

    monkeypatch.setattr(TrackingContext, "_persist_to_database", _persist)
    monkeypatch.setattr(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        lambda *_a, **_k: (Decimal("0.002"), Decimal("0.0018"), Decimal("0.91")),
    )
    return seen


def _google(status: int, body: bytes = b"png") -> AsyncMock:
    response = httpx.Response(status, content=body, headers={"content-type": "image/png"})
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__.return_value = client
    return client


async def _serve(run: str | None, sig: str | None, user_id: uuid.UUID) -> StreamingResponse:
    return await mod.serve_billed_image(
        "https://maps.googleapis.com/x",
        api_name="static_maps",
        endpoint="/staticmap",
        service="google_routes",
        operation="static_map",
        timeout=5.0,
        default_media_type="image/png",
        user_id=user_id,
        run=run,
        sig=sig,
    )


def _signed_params(run_id: str, user_id: uuid.UUID) -> tuple[str, str]:
    token = current_tracker.set(TrackingContext(run_id, user_id, "s", None))
    try:
        query = with_attribution("/p").split("?", 1)[1]
    finally:
        current_tracker.reset(token)
    params = dict(part.split("=", 1) for part in query.split("&"))
    return params["run"], params["sig"]


async def test_a_served_image_is_counted_on_the_turn_that_asked(
    persisted: list[TrackingContext], usage_check: AsyncMock
) -> None:
    user_id = uuid.uuid4()
    run, sig = _signed_params("turn-42", user_id)
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        response = await _serve(run, sig, user_id)
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "private, max-age=86400"
    (tracker,) = persisted
    assert tracker.run_id == "turn-42"
    assert tracker.user_id == user_id
    # ``_persist_to_database`` is stubbed, so the records are still held:
    assert tracker.pending_families()["google_api"] == 1
    assert tracker.get_summary()["google_api_cost_eur"] == pytest.approx(0.0018)
    usage_check.assert_awaited_once_with(user_id)


async def test_an_unsigned_fetch_is_counted_on_a_fresh_run_of_the_caller(
    persisted: list[TrackingContext],
) -> None:
    user_id = uuid.uuid4()
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        await _serve("turn-42", None, user_id)
    (tracker,) = persisted
    assert tracker.run_id.startswith("media_")
    assert tracker.user_id == user_id
    assert tracker.pending_families()["google_api"] == 1


async def test_a_refused_request_is_not_billed_and_not_counted(
    persisted: list[TrackingContext],
) -> None:
    user_id = uuid.uuid4()
    with (
        patch.object(httpx, "AsyncClient", return_value=_google(403, b"denied")),
        pytest.raises(ExternalServiceError),
    ):
        await _serve(None, None, user_id)
    assert persisted == []


async def test_the_count_is_persisted_before_the_bytes_are_returned(
    persisted: list[TrackingContext],
) -> None:
    """The tracker closes inside the helper: nothing is left for a caller to flush."""
    user_id = uuid.uuid4()
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        await _serve(None, None, user_id)
    assert len(persisted) == 1
    assert current_tracker.get() is None


@pytest.mark.parametrize(
    "status", [UsageLimitStatus.BLOCKED_LIMIT, UsageLimitStatus.BLOCKED_INSTANCE_BUDGET]
)
async def test_a_blocked_budget_refuses_media_before_creating_a_provider_client(
    status: UsageLimitStatus, usage_check: AsyncMock, persisted: list[TrackingContext]
) -> None:
    user_id = uuid.uuid4()
    usage_check.return_value = UsageLimitCheckResult(
        False, status, "Budget exhausted", "cycle_cost"
    )
    with patch.object(httpx, "AsyncClient") as provider:
        with pytest.raises(UsageLimitExceededError) as refusal:
            await _serve(None, None, user_id)
        provider.assert_not_called()
    usage_check.assert_awaited_once_with(user_id)
    assert persisted == []
    assert current_tracker.get() is None
    assert refusal.value.status_code == 429
    if status is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET:
        assert refusal.value.error_code == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
        assert int(refusal.value.headers["Retry-After"]) > 0


MediaKind = Literal["route", "location", "street", "photo"]


async def _proxy(kind: MediaKind, user: User) -> StreamingResponse:
    if kind == "route":
        return await mod.proxy_routes_static_map("encoded", current_user=user)
    if kind == "location":
        return await mod.proxy_location_static_map("48.85", "2.35", current_user=user)
    if kind == "street":
        return await mod.proxy_street_view("48.85,2.35", current_user=user)
    with patch.object(routes.ConnectorService, "is_places_enabled", AsyncMock(return_value=True)):
        return await routes.proxy_places_photo(
            "places/example/photos/example", current_user=user, db=AsyncMock(spec=AsyncSession)
        )


@pytest.mark.parametrize("kind", ["route", "location", "street", "photo"])
async def test_every_media_endpoint_preserves_the_canonical_budget_refusal(
    kind: MediaKind,
    usage_check: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    persisted: list[TrackingContext],
) -> None:
    monkeypatch.setattr(mod.settings, "google_api_key", "test-key")
    monkeypatch.setattr(mod.settings, "street_view_enabled", True)
    user = User(id=uuid.uuid4(), email="card-test@example.test")
    usage_check.return_value = UsageLimitCheckResult(
        False, UsageLimitStatus.BLOCKED_INSTANCE_BUDGET, "Budget exhausted", "instance_daily_budget"
    )
    with patch.object(httpx, "AsyncClient") as provider:
        with pytest.raises(UsageLimitExceededError) as refusal:
            await _proxy(kind, user)
        provider.assert_not_called()
    assert refusal.value.status_code == 429
    assert refusal.value.error_code == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
    assert int(refusal.value.headers["Retry-After"]) > 0
    assert persisted == []


@pytest.mark.parametrize("kind", ["route", "street"])
async def test_invalid_coordinates_remain_a_client_error_without_spending(
    kind: MediaKind,
    usage_check: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod.settings, "google_api_key", "test-key")
    monkeypatch.setattr(mod.settings, "street_view_enabled", True)
    user = User(id=uuid.uuid4(), email="card-test@example.test")
    with patch.object(httpx, "AsyncClient") as provider:
        with pytest.raises(ValidationError) as refusal:
            if kind == "route":
                await mod.proxy_routes_static_map(
                    "encoded", origin="&key=injected", current_user=user
                )
            else:
                await mod.proxy_street_view("&key=injected", current_user=user)
        provider.assert_not_called()
    assert refusal.value.status_code == 400
    usage_check.assert_not_awaited()


@pytest.mark.parametrize("kind", ["route", "location", "street", "photo"])
async def test_network_failure_preserves_service_error_without_logging_the_api_key(
    kind: MediaKind,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    persisted: list[TrackingContext],
) -> None:
    secret = "must-not-appear-in-proxy-logs"
    monkeypatch.setattr(mod.settings, "google_api_key", secret)
    monkeypatch.setattr(mod.settings, "street_view_enabled", True)
    user = User(id=uuid.uuid4(), email="card-test@example.test")
    client = _google(200)
    client.get.side_effect = httpx.RequestError(
        f"Connection failed for https://maps.googleapis.com/x?key={secret}"
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        with pytest.raises(ExternalServiceError) as failure:
            await _proxy(kind, user)
    assert failure.value.status_code == 503
    assert secret not in caplog.text
    assert persisted == []
    assert current_tracker.get() is None


@pytest.mark.parametrize(
    "path",
    [
        "/google-routes/static-map?polyline=encoded",
        "/google-location/static-map?lat=48.85&lng=2.35",
        "/street-view?location=48.85,2.35",
        "/photo?photo_name=places/example/photos/example",
    ],
)
def test_budget_refusal_crosses_the_http_boundary_with_retry_after(
    path: str,
    usage_check: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real FastAPI dependency/error serialization; DB and Google stay hermetic."""
    monkeypatch.setattr(mod.settings, "google_api_key", "test-key")
    monkeypatch.setattr(mod.settings, "street_view_enabled", True)
    user = User(id=uuid.uuid4(), email="card-test@example.test")
    app = FastAPI()
    app.include_router(mod.media_proxy_router)
    app.add_api_route("/photo", routes.proxy_places_photo, methods=["GET"])
    app.dependency_overrides[get_current_active_session] = lambda: user
    app.dependency_overrides[mod.rate_limit_static_map] = lambda: None
    app.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    usage_check.return_value = UsageLimitCheckResult(
        False, UsageLimitStatus.BLOCKED_INSTANCE_BUDGET, "Budget exhausted", "instance_daily_budget"
    )
    with (
        patch.object(routes.ConnectorService, "is_places_enabled", AsyncMock(return_value=True)),
        patch.object(httpx, "AsyncClient") as provider,
        TestClient(app) as client,
    ):
        response = client.get(path)
        provider.assert_not_called()
    assert response.status_code == 429
    assert response.json()["detail"]["error_code"] == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
    assert int(response.headers["Retry-After"]) > 0
    usage_check.assert_awaited_once_with(user.id)
