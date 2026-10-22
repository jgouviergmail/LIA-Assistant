"""An explicit map selection computes one route, under its own durable ledger."""

import asyncio
import math
import re
from datetime import UTC
from typing import TypeGuard
from uuid import UUID, uuid4

from langchain.tools import ToolRuntime

from src.core.config import settings
from src.core.exceptions import (
    BaseAPIException,
    ExternalServiceError,
    raise_configuration_missing,
    raise_permission_denied,
)
from src.core.geo_utils import haversine_distance
from src.domains.agents.api.schemas import BrowserContext, BrowserGeolocation
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.location_resolution import (
    ResolvedLocation,
    resolve_implicit_location,
)
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_routes_client import (
    GoogleRoutesClient,
    TravelMode,
    route_request_features,
    routes_sku_suffix,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.place_route_schemas import PlaceRouteRequest, PlaceRouteResponse
from src.domains.connectors.repository import ConnectorRepository
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
from src.domains.usage_limits.service import UsageLimitService
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.database.session import get_db_context

PLACE_ROUTE_WALK_MAX_DISTANCE_METERS = 2000


async def check_route_access(user_id: UUID) -> None:
    """Read the administrator's switch, then both existing spend ceilings.

    Routes tools require the platform key, never a per-account activation row
    (``ConnectorType`` documents this exception to keyless provisioning).
    The global switch still applies to this explicit route surface.
    """
    if not settings.google_api_key.strip():
        raise_configuration_missing("google_routes", "api_key")
    async with get_db_context() as db:
        config = await ConnectorRepository(db).get_global_config_by_type(
            ConnectorType.GOOGLE_ROUTES
        )
        enabled = config is None or config.is_enabled
    if not enabled:
        raise_permission_denied(action="use", resource_type="google_routes connector")
    verdict = await UsageLimitService.check_user_allowed(user_id)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer="place_route")


def _noop_writer(_: object) -> None:
    """The shared location resolver needs no streaming writer."""


def _location_runtime(
    body: PlaceRouteRequest, user_id: UUID, run_id: str
) -> ToolRuntime[LiaRuntimeContext | None, dict[str, object]]:
    """Adapt the HTTP identity to the existing cascade, as the skill runner does."""
    origin = body.origin
    browser_context = (
        BrowserContext(
            geolocation=BrowserGeolocation(
                lat=origin.lat,
                lon=origin.lon,
                accuracy=origin.accuracy,
                timestamp=int(origin.timestamp),
            )
        )
        if origin is not None
        else None
    )
    return ToolRuntime(
        state={},
        context=LiaRuntimeContext(
            user_id=user_id,
            thread_id=run_id,
            conversation_id=run_id,
            browser_context=browser_context,
        ),
        config={},
        stream_writer=_noop_writer,
        tool_call_id=None,
        store=None,
    )


async def _settle(
    tracker: TrackingContext,
    client: GoogleRoutesClient,
    run_id: str,
    pending_commit: asyncio.Task[None] | None = None,
) -> None:
    """Always close and release records; never acknowledge an unfiled paid call."""
    try:
        # The same intermediate write must finish before another commit can
        # start, even if repeated cancellation exhausted its first grace window.
        if pending_commit is not None:
            await pending_commit
        await tracker.commit(strict=True)
    finally:
        try:
            await client.close()
        finally:
            TrackingContext.cleanup_run_records(run_id)


def _project_route(data: object, origin: ResolvedLocation, mode: TravelMode) -> PlaceRouteResponse:
    """Keep usable display facts; the caller settles accounting before any exit."""
    try:
        if not isinstance(data, dict):
            raise ValueError("Invalid routes payload")
        routes = data.get("routes")
        if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
            raise ValueError("No route found")
        route = routes[0]
        duration = route.get("duration")
        if (
            not isinstance(duration, str)
            or re.fullmatch(r"\d{1,10}(?:\.\d{1,9})?s", duration) is None
        ):
            raise ValueError("Invalid route duration")
        polyline = route.get("polyline")
        as_of = origin.as_of
        if origin.source == "last_known" and as_of is None:
            raise ValueError("Last-known location age is unavailable")
        return PlaceRouteResponse.model_validate(
            {
                "origin_source": origin.source,
                "origin_as_of": (
                    as_of.replace(tzinfo=UTC).isoformat()
                    if as_of is not None and as_of.tzinfo is None
                    else as_of.isoformat() if as_of is not None else None
                ),
                "travel_mode": mode.value,
                "polyline": polyline.get("encodedPolyline") if isinstance(polyline, dict) else None,
                "distance_meters": route.get("distanceMeters"),
                "duration_seconds": math.ceil(float(duration[:-1])),
            }
        )
    except ValueError as exc:
        raise ExternalServiceError(
            service_name="google_routes", detail="No usable route is available"
        ) from exc


def _usable_origin(origin: ResolvedLocation | None) -> TypeGuard[ResolvedLocation]:
    """Validate the shared cascade's point before using any paid route capability."""
    return (
        origin is not None
        and origin.source in ("browser", "last_known", "home")
        and math.isfinite(origin.lat)
        and -90 <= origin.lat <= 90
        and math.isfinite(origin.lon)
        and -180 <= origin.lon <= 180
        and (origin.source != "last_known" or origin.as_of is not None)
    )


def _require_route_price(mode: TravelMode) -> None:
    """Quote the features the client sends, including any corrective drive call."""
    endpoint = "/directions/v2:computeRoutes" + routes_sku_suffix(route_request_features(mode))
    usd, eur, _ = GoogleApiPricingService.get_cost_per_request("routes", endpoint)
    if usd <= 0 or eur <= 0:
        raise_configuration_missing("google_routes", "pricing")


async def _request_route(
    client: GoogleRoutesClient,
    body: PlaceRouteRequest,
    origin: ResolvedLocation,
    mode: TravelMode,
) -> PlaceRouteResponse:
    data = await client.compute_route(
        origin={"lat": origin.lat, "lon": origin.lon},
        destination={"lat": body.destination.lat, "lon": body.destination.lng},
        travel_mode=mode,
    )
    return _project_route(data, origin, mode)


async def compute_place_route(
    body: PlaceRouteRequest, user_id: UUID, language: str | None = None
) -> PlaceRouteResponse:
    """Compute a bounded selected route with no open database session during I/O."""
    await check_route_access(user_id)
    run_id = f"place_route_{uuid4().hex}"
    origin = await resolve_implicit_location(_location_runtime(body, user_id, run_id))
    if not _usable_origin(origin):
        raise BaseAPIException(
            status_code=422,
            detail={
                "code": "place_route_origin_unavailable",
                "message": "No current, fresh saved or home position is available",
            },
        )
    estimated_meters = (
        haversine_distance(origin.lat, origin.lon, body.destination.lat, body.destination.lng)
        * 1000
    )
    mode = (
        TravelMode.WALK
        if estimated_meters <= PLACE_ROUTE_WALK_MAX_DISTANCE_METERS
        else TravelMode.DRIVE
    )
    _require_route_price(mode)
    client = GoogleRoutesClient(language=language, user_id=user_id)
    pending_commit: asyncio.Task[None] | None = None
    async with TrackingContext(
        run_id, user_id, "interactive_place_route", None, auto_commit=False
    ) as tracker:
        try:
            async with asyncio.timeout(settings.http_timeout_routes_api):
                result = await _request_route(client, body, origin, mode)
                if (
                    mode is TravelMode.WALK
                    and result.distance_meters > PLACE_ROUTE_WALK_MAX_DISTANCE_METERS
                ):
                    # File WALK first so both ceilings can see the paid call.
                    # Keep its exact task: a cancellation may outlive the first
                    # grace window, and settlement must never re-file its rows.
                    walk_commit = asyncio.create_task(tracker.commit(strict=True))
                    pending_commit = walk_commit
                    if await write_through_cancellation(
                        lambda: walk_commit, attempts=3, label="place_route_walk_commit"
                    ):
                        raise asyncio.CancelledError()
                    await check_route_access(user_id)
                    _require_route_price(TravelMode.DRIVE)
                    result = await _request_route(client, body, origin, TravelMode.DRIVE)
        except TimeoutError as exc:
            raise ExternalServiceError(
                service_name="google_routes",
                detail="Google Routes API timed out",
                error_type="timeout",
            ) from exc
        finally:
            # One registered task survives repeated cancellation deliveries;
            # never start a second commit or return while its cleanup runs.
            cancelled = await write_through_cancellation(
                lambda: _settle(tracker, client, run_id, pending_commit),
                attempts=3,
                label="place_route_settlement",
            )
            if cancelled:
                raise asyncio.CancelledError()
    return result
