"""Private home preferences; no caller-selected account and no shared DTO."""

from fastapi import APIRouter, Depends

from src.core.exceptions import CacheError
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.world.home import HomeUpdate, HomeView
from src.domains.world.home_service import read_owner_home, update_owner_home

router = APIRouter(
    prefix="/home",
    route_class=PrivateApplicationInputRoute,
    dependencies=capability_dependencies(PlatformCapability.WORLD),
)
_write_limit = create_user_rate_limiter(
    "world_home", max_calls=20, authenticate=get_current_active_session_for_stream
)


@router.get("", response_model=HomeView)
async def get_home(
    user: User = Depends(get_current_active_session_for_stream),
) -> HomeView:
    """Return only the authenticated account's private home colours."""
    try:
        return await read_owner_home(user.id)
    except TimeoutError as exc:
        raise CacheError("world_home") from exc


@router.put("", response_model=HomeView, dependencies=[Depends(_write_limit)])
async def put_home(
    payload: HomeUpdate, user: User = Depends(get_current_active_session_for_stream)
) -> HomeView:
    """Save only the authenticated account's revision-fenced home colour edit."""
    try:
        return await update_owner_home(user.id, payload)
    except TimeoutError as exc:
        raise CacheError("world_home") from exc
