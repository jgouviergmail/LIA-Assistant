"""Private owner-only experience preferences through native session and capability guards."""

from fastapi import APIRouter, Depends

from src.core.exceptions import CacheError
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.world.experience import ExperienceUpdate, ExperienceView
from src.domains.world.experience_service import read_owner_experience, update_owner_experience

router = APIRouter(
    prefix="/experience",
    route_class=PrivateApplicationInputRoute,
    dependencies=capability_dependencies(PlatformCapability.WORLD),
)
_write_limit = create_user_rate_limiter(
    "world_experience", max_calls=20, authenticate=get_current_active_session_for_stream
)


@router.get("", response_model=ExperienceView)
async def get_experience(
    user: User = Depends(get_current_active_session_for_stream),
) -> ExperienceView:
    """Read only the authenticated owner's private presentation preferences.

    Args:
        user: The authenticated owner.

    Returns:
        The owner's preferences, defaults when never saved, flagged when the
        stored document needs the explicit repair.

    Raises:
        CacheError: The bounded policy deadline expired.
    """
    try:
        return await read_owner_experience(user.id)
    except TimeoutError as exc:
        raise CacheError("world_experience") from exc


@router.put("", response_model=ExperienceView, dependencies=[Depends(_write_limit)])
async def put_experience(
    payload: ExperienceUpdate, user: User = Depends(get_current_active_session_for_stream)
) -> ExperienceView:
    """Save only the authenticated owner's revision-fenced preference edits.

    Args:
        payload: The edited fields, the observed revision, or an explicit repair.
        user: The authenticated owner.

    Returns:
        The saved preferences under their new revision.

    Raises:
        CacheError: The bounded policy deadline expired.
    """
    try:
        return await update_owner_experience(user.id, payload)
    except TimeoutError as exc:
        raise CacheError("world_experience") from exc
