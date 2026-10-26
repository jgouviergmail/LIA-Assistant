"""Account-owned appearance with native admission, privacy and write limits."""

from fastapi import APIRouter, Depends

from src.core.exceptions import CacheError
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.world.avatar import AvatarUpdate, AvatarView
from src.domains.world.avatar_presence import refresh_avatar_presence
from src.domains.world.avatar_service import read_owner_avatar, update_owner_avatar

router = APIRouter(
    prefix="/avatar",
    route_class=PrivateApplicationInputRoute,
    dependencies=capability_dependencies(PlatformCapability.WORLD),
)
write_limit = create_user_rate_limiter(
    "world_avatar", max_calls=20, authenticate=get_current_active_session_for_stream
)


@router.get("", response_model=AvatarView)
async def get_avatar(
    user: User = Depends(get_current_active_session_for_stream),
) -> AvatarView:
    """Return only the authenticated account's private avatar preferences."""
    try:
        return await read_owner_avatar(user.id)
    except TimeoutError as exc:
        raise CacheError("world_avatar") from exc


@router.put("", response_model=AvatarView, dependencies=[Depends(write_limit)])
async def put_avatar(
    payload: AvatarUpdate, user: User = Depends(get_current_active_session_for_stream)
) -> AvatarView:
    """Save only the authenticated account's revision-fenced public appearance edit."""
    try:
        result = await update_owner_avatar(user.id, payload)
    except TimeoutError as exc:
        raise CacheError("world_avatar") from exc
    await refresh_avatar_presence(user.id, result.preferences)
    return result
