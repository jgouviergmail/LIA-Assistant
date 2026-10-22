"""Authenticated, explicit route computation for the Position map."""

from fastapi import APIRouter, Depends, Response

from src.core.constants import RATE_LIMIT_PLACE_ROUTE_PER_MINUTE
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.connectors.place_route_schemas import PlaceRouteRequest, PlaceRouteResponse
from src.domains.connectors.place_route_service import compute_place_route
from src.domains.users.models import User

place_route_router = APIRouter()
rate_limit_place_route = create_user_rate_limiter(
    "place_route",
    RATE_LIMIT_PLACE_ROUTE_PER_MINUTE,
    authenticate=get_current_active_session_for_stream,
)


@place_route_router.post(
    "/google-maps/place-route",
    response_model=PlaceRouteResponse,
    dependencies=[Depends(rate_limit_place_route)],
)
async def place_route(
    body: PlaceRouteRequest,
    response: Response,
    user: User = Depends(get_current_active_session_for_stream),
) -> PlaceRouteResponse:
    """Compute the route to a place selected on the Position map, never cached."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return await compute_place_route(body, user.id, user.language)
