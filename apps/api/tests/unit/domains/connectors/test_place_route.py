"""The Position map's route seam is bounded, attributed and independent of a chat turn."""

import asyncio
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.agents.tools.location_resolution import ResolvedLocation
from src.domains.connectors import place_route_service as service
from src.domains.connectors.place_route_router import place_route_router
from src.domains.connectors.place_route_schemas import PlaceRouteRequest, PlaceRouteResponse

pytestmark = pytest.mark.unit
POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def request(**overrides):
    return PlaceRouteRequest.model_validate(
        {"destination": {"lat": 48.85, "lng": 2.35}, **overrides}
    )


@pytest.fixture
def runtime(monkeypatch):
    events = []
    tracker = MagicMock()
    tracker.commit = AsyncMock(side_effect=lambda **_: events.append("commit"))
    tracker.__aenter__ = AsyncMock(return_value=tracker)
    tracker.__aexit__ = AsyncMock(return_value=False)
    tracking = MagicMock(return_value=tracker)
    tracking.cleanup_run_records.side_effect = lambda _: events.append("cleanup")
    monkeypatch.setattr(service, "TrackingContext", tracking)
    client = MagicMock()
    client.compute_route = AsyncMock(
        return_value={
            "routes": [
                {
                    "polyline": {"encodedPolyline": POLYLINE},
                    "distanceMeters": 123,
                    "duration": "12.3s",
                    "provider_private": "never expose",
                }
            ]
        }
    )
    client.close = AsyncMock(side_effect=lambda: events.append("close"))
    monkeypatch.setattr(service, "GoogleRoutesClient", MagicMock(return_value=client))
    monkeypatch.setattr(service, "check_route_access", AsyncMock())
    monkeypatch.setattr(
        service,
        "resolve_implicit_location",
        AsyncMock(return_value=ResolvedLocation(48.85, 2.351, "browser")),
    )
    monkeypatch.setattr(
        service.GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.01"), Decimal("0.009"), Decimal("0.9")),
    )
    return SimpleNamespace(client=client, tracker=tracker, tracking=tracking, events=events)


@pytest.mark.parametrize(
    "payload",
    [
        {"destination": {"lat": 91, "lng": 0}},
        {"destination": {"lat": 0, "lng": -181}},
        {"destination": {"lat": "48", "lng": 0}},
        {"destination": {"lat": True, "lng": 0}},
        {"destination": {"lat": float("nan"), "lng": 0}},
        {"destination": {"lat": 0, "lng": float("inf")}},
        {"destination": {"lat": 0, "lng": 0, "address": "invented"}},
        {"destination": {"lat": 0, "lng": 0}, "user_id": str(uuid4())},
    ],
)
def test_request_rejects_unbounded_or_coerced_coordinates(payload):
    with pytest.raises(ValidationError):
        PlaceRouteRequest.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"timestamp": None},
        {"timestamp": lambda: time.time() * 1000 - 301_000},
        {"timestamp": lambda: time.time() * 1000 + 60_000},
        {"timestamp": True},
        {"timestamp": float("nan")},
        {"accuracy": -1},
        {"accuracy": float("inf")},
        {"lon": 181},
    ],
)
def test_browser_origin_requires_finite_fresh_capture(change):
    change = {key: value() if callable(value) else value for key, value in change.items()}
    with pytest.raises(ValidationError):
        request(origin={"lat": 48.85, "lon": 2.35, "timestamp": time.time() * 1000, **change})


@pytest.mark.parametrize("offset_ms", [1, 30_000, -300_000])
def test_browser_capture_accepts_bounded_clock_skew_without_extending_age(monkeypatch, offset_ms):
    import src.domains.connectors.place_route_schemas as schemas

    monkeypatch.setattr(schemas.time, "time", lambda: 1_800_000_000)
    body = request(origin={"lat": 48.85, "lon": 2.35, "timestamp": 1_800_000_000_000 + offset_ms})
    assert body.origin.timestamp == 1_800_000_000_000 + offset_ms


@pytest.mark.parametrize("offset_ms", [30_001, -300_001])
def test_browser_capture_rejects_beyond_clock_skew_and_age_bounds(monkeypatch, offset_ms):
    import src.domains.connectors.place_route_schemas as schemas

    monkeypatch.setattr(schemas.time, "time", lambda: 1_800_000_000)
    with pytest.raises(ValidationError):
        request(origin={"lat": 48.85, "lon": 2.35, "timestamp": 1_800_000_000_000 + offset_ms})


async def test_route_is_projected_and_metered_once_with_a_fresh_run(runtime):
    owner = uuid4()
    result = await service.compute_place_route(request(), owner)
    assert result.model_dump() == {
        "origin_source": "browser",
        "origin_as_of": None,
        "travel_mode": "WALK",
        "polyline": POLYLINE,
        "distance_meters": 123,
        "duration_seconds": 13,
    }
    runtime.tracking.assert_called_once()
    args, kwargs = runtime.tracking.call_args
    assert args[0].startswith("place_route_") and args[1] == owner
    assert args[3] is None and kwargs == {"auto_commit": False}
    runtime.tracker.commit.assert_awaited_once_with(strict=True)
    assert runtime.events == ["commit", "close", "cleanup"]


async def test_last_known_age_is_explicit_and_home_is_not_a_live_position(runtime, monkeypatch):
    captured = datetime(2026, 10, 19, 10, tzinfo=UTC)
    for source, as_of in [("last_known", captured), ("home", None)]:
        service.resolve_implicit_location.return_value = ResolvedLocation(
            49.0, 2.35, source, as_of=as_of
        )
        response = await service.compute_place_route(request(), uuid4())
        assert response.origin_source == source
        assert response.origin_as_of == (captured.isoformat() if as_of else None)
        assert response.travel_mode == "DRIVE"


async def test_browser_runtime_uses_owner_and_shared_cascade(runtime):
    owner = uuid4()
    origin = {"lat": 48.8, "lon": 2.3, "accuracy": None, "timestamp": time.time() * 1000}
    await service.compute_place_route(request(origin=origin), owner)
    tool_runtime = service.resolve_implicit_location.call_args.args[0]
    assert tool_runtime.context.user_id == owner
    assert tool_runtime.context.browser_context.geolocation.lat == origin["lat"]
    assert tool_runtime.context.browser_context.geolocation.lon == origin["lon"]


@pytest.mark.parametrize(
    "distance_km,expected", [(0, "WALK"), (1.999, "WALK"), (2.0, "WALK"), (2.001, "DRIVE")]
)
@pytest.mark.parametrize("source", ["browser", "last_known", "home"])
async def test_selected_place_mode_uses_inclusive_two_km_server_distance(
    runtime, monkeypatch, distance_km, expected, source
):
    origin = ResolvedLocation(
        48.85, 2.351, source, as_of=datetime.now(UTC) if source == "last_known" else None
    )
    service.resolve_implicit_location.return_value = origin
    distance = MagicMock(return_value=distance_km)
    monkeypatch.setattr(service, "haversine_distance", distance)
    # The interactive map's explicit rule is independent of generic route defaults.
    monkeypatch.setattr(service.settings, "routes_walk_threshold_km", 0.1)
    result = await service.compute_place_route(request(), uuid4())
    assert result.travel_mode == expected
    assert runtime.client.compute_route.call_args.kwargs["travel_mode"].value == expected
    distance.assert_called_once_with(origin.lat, origin.lon, 48.85, 2.35)


def test_request_cannot_override_the_server_travel_mode():
    with pytest.raises(ValidationError):
        request(travel_mode="WALK")


async def test_no_origin_is_machine_readable_and_never_calls_google(runtime):
    service.resolve_implicit_location.return_value = None
    with pytest.raises(BaseAPIException) as error:
        await service.compute_place_route(request(), uuid4())
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "place_route_origin_unavailable"
    runtime.client.compute_route.assert_not_awaited()
    runtime.tracking.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"routes": []},
        {"routes": [{}]},
        {
            "routes": [
                {"distanceMeters": -1, "duration": "1s", "polyline": {"encodedPolyline": POLYLINE}}
            ]
        },
        {
            "routes": [
                {"distanceMeters": 1, "duration": "NaNs", "polyline": {"encodedPolyline": POLYLINE}}
            ]
        },
        {
            "routes": [
                {
                    "distanceMeters": True,
                    "duration": "1s",
                    "polyline": {"encodedPolyline": POLYLINE},
                }
            ]
        },
        {
            "routes": [
                {
                    "distanceMeters": 1,
                    "duration": "1s",
                    "polyline": {"encodedPolyline": "~" * 50_001},
                }
            ]
        },
    ],
)
async def test_paid_unusable_results_still_commit_and_close(runtime, payload):
    runtime.client.compute_route.return_value = payload
    with pytest.raises(BaseAPIException) as error:
        await service.compute_place_route(request(), uuid4())
    assert error.value.status_code == 503
    assert runtime.events == ["commit", "close", "cleanup"]
    runtime.client.compute_route.assert_awaited_once()


@pytest.mark.parametrize("error", [RuntimeError("provider failed"), asyncio.CancelledError()])
async def test_error_and_cancellation_settle_accounting_and_close(runtime, error):
    runtime.client.compute_route.side_effect = error
    with pytest.raises(type(error)):
        await service.compute_place_route(request(), uuid4())
    assert runtime.events == ["commit", "close", "cleanup"]


async def test_failed_durable_accounting_cannot_acknowledge_a_route(runtime):
    runtime.tracker.commit.side_effect = RuntimeError("durable ledger unavailable")
    with pytest.raises(RuntimeError, match="durable ledger"):
        await service.compute_place_route(request(), uuid4())
    runtime.client.close.assert_awaited_once()
    runtime.tracking.cleanup_run_records.assert_called_once()


async def test_repeated_cancellation_waits_for_one_commit_and_one_close(runtime):
    commit_started, release_commit = asyncio.Event(), asyncio.Event()
    close_started, release_close = asyncio.Event(), asyncio.Event()

    async def commit(**_):
        runtime.events.append("commit-start")
        commit_started.set()
        await release_commit.wait()
        runtime.events.append("commit-done")

    async def close():
        runtime.events.append("close-start")
        close_started.set()
        await release_close.wait()
        runtime.events.append("close-done")

    runtime.tracker.commit.side_effect = commit
    runtime.client.close.side_effect = close
    task = asyncio.create_task(service.compute_place_route(request(), uuid4()))
    try:
        await asyncio.wait_for(commit_started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        waited_during_commit = not task.done()
        release_commit.set()
        await asyncio.wait_for(close_started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        waited_during_close = not task.done()
    finally:
        release_commit.set()
        release_close.set()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
    assert waited_during_commit and waited_during_close
    assert runtime.events == ["commit-start", "commit-done", "close-start", "close-done", "cleanup"]
    runtime.tracker.commit.assert_awaited_once_with(strict=True)
    runtime.client.close.assert_awaited_once()


def test_new_wire_fields_explain_their_meaning():
    from src.domains.connectors.place_route_schemas import RouteBrowserOrigin, RouteDestination

    for model in (RouteDestination, RouteBrowserOrigin, PlaceRouteRequest, PlaceRouteResponse):
        assert all(field.description for field in model.model_fields.values()), model.__name__


async def test_missing_price_refuses_before_paid_call(runtime, monkeypatch):
    monkeypatch.setattr(
        service.GoogleApiPricingService, "get_cost_per_request", lambda *_: (0, 0, 1)
    )
    with pytest.raises(BaseAPIException):
        await service.compute_place_route(request(), uuid4())
    runtime.client.compute_route.assert_not_awaited()


async def test_network_deadline_is_a_provider_failure_and_still_settles(runtime, monkeypatch):
    async def delayed(**_):
        await asyncio.sleep(0.1)

    monkeypatch.setattr(service.settings, "http_timeout_routes_api", 0.001)
    runtime.client.compute_route.side_effect = delayed
    with pytest.raises(BaseAPIException) as error:
        await service.compute_place_route(request(), uuid4())
    assert error.value.status_code == 503
    assert runtime.events == ["commit", "close", "cleanup"]


@pytest.mark.parametrize("lat,lon", [(float("nan"), 2.35), (91, 2.35), (48.85, float("inf"))])
async def test_invalid_persisted_origin_never_reaches_google(runtime, lat, lon):
    service.resolve_implicit_location.return_value = ResolvedLocation(lat, lon, "home")
    with pytest.raises(BaseAPIException) as error:
        await service.compute_place_route(request(), uuid4())
    assert error.value.detail["code"] == "place_route_origin_unavailable"
    runtime.client.compute_route.assert_not_awaited()


@pytest.mark.parametrize("empty", [False, True])
async def test_real_client_emits_paid_record_to_real_tracker_before_projection(monkeypatch, empty):
    import httpx

    from src.domains.chat.service import TrackingContext

    monkeypatch.setattr(service, "check_route_access", AsyncMock())
    monkeypatch.setattr(
        service,
        "resolve_implicit_location",
        AsyncMock(return_value=ResolvedLocation(48.85, 2.351, "browser")),
    )
    monkeypatch.setattr(service.settings, "google_api_key", "server-only")
    monkeypatch.setattr(
        service.GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.01"), Decimal("0.009"), Decimal("0.9")),
    )
    routes = (
        []
        if empty
        else [{"distanceMeters": 0, "duration": "0s", "polyline": {"encodedPolyline": "????"}}]
    )
    transport = SimpleNamespace(
        post=AsyncMock(return_value=httpx.Response(200, json={"routes": routes})),
        is_closed=False,
        aclose=AsyncMock(),
    )
    client = service.GoogleRoutesClient()
    client._client = transport
    monkeypatch.setattr(service, "GoogleRoutesClient", MagicMock(return_value=client))
    persisted = []

    async def persist(tracker):
        persisted.append(
            (tracker.user_id, tracker.run_id, tracker.get_google_api_calls_breakdown())
        )

    monkeypatch.setattr(TrackingContext, "_persist_to_database", persist)
    owner = uuid4()
    if empty:
        with pytest.raises(BaseAPIException):
            await service.compute_place_route(request(), owner)
    else:
        result = await service.compute_place_route(request(), owner)
        assert result.distance_meters == result.duration_seconds == 0
    assert len(persisted) == 1
    assert persisted[0][0] == owner and persisted[0][1].startswith("place_route_")
    assert persisted[0][2] == [
        {
            "api_name": "routes",
            "endpoint": "/directions/v2:computeRoutes",
            "cost_usd": 0.01,
            "cost_eur": 0.009,
            "cached": False,
        }
    ]
    transport.aclose.assert_awaited_once()


async def test_access_checks_both_quota_ceilings_and_admin_switch(monkeypatch):
    monkeypatch.setattr(service.settings, "google_api_key", "server-only")
    allowed = AsyncMock(return_value=SimpleNamespace(allowed=True))
    monkeypatch.setattr(service.UsageLimitService, "check_user_allowed", allowed)
    repo = MagicMock()
    repo.get_global_config_by_type = AsyncMock(return_value=SimpleNamespace(is_enabled=False))
    monkeypatch.setattr(service, "ConnectorRepository", MagicMock(return_value=repo))
    opened = []

    @asynccontextmanager
    async def db_context():
        opened.append(True)
        try:
            yield MagicMock()
        finally:
            opened.pop()

    monkeypatch.setattr(service, "get_db_context", db_context)
    with pytest.raises(BaseAPIException) as error:
        await service.check_route_access(uuid4())
    assert error.value.status_code == 403 and not opened
    repo.get_global_config_by_type.return_value = None
    owner = uuid4()
    await service.check_route_access(owner)
    allowed.assert_awaited_once_with(owner)
    allowed.return_value = SimpleNamespace(
        allowed=False, exceeded_limit="cost", blocked_reason="budget"
    )
    with pytest.raises(BaseAPIException) as error:
        await service.check_route_access(owner)
    assert error.value.status_code == 429


async def test_access_missing_server_key_refuses_without_database(monkeypatch):
    monkeypatch.setattr(service.settings, "google_api_key", "")
    db = MagicMock()
    monkeypatch.setattr(service, "get_db_context", db)
    with pytest.raises(BaseAPIException):
        await service.check_route_access(uuid4())
    db.assert_not_called()


async def test_endpoint_requires_authentication_and_uses_detached_identity(monkeypatch, runtime):
    import src.domains.connectors.place_route_router as router_module

    app = FastAPI()
    app.include_router(place_route_router, prefix="/connectors")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/connectors/google-maps/place-route", json=request().model_dump()
        )
    assert response.status_code == 401
    owner = SimpleNamespace(id=uuid4(), language="fr")
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: owner
    app.dependency_overrides[router_module.rate_limit_place_route] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/connectors/google-maps/place-route", json=request().model_dump()
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "server-only" not in response.text
    PlaceRouteResponse.model_validate(response.json())
