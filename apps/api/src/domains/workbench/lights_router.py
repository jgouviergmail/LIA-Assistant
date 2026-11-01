"""Routes of the « Tools » lights screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
The bridge is read under the read window; a change is set under the write
window and answers nothing — the screen keeps what it drew, and restores it
when the change is refused.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.workbench import lights_service
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.lights import LightChange, LightsView, RoomChange, SceneRecall

router = APIRouter(prefix="/lights")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.get(
    "",
    response_model=LightsView,
    summary="The account's bridge: its rooms, lights and scenes",
    dependencies=[Depends(rate_limit_read)],
)
async def get_lights(user: _Account) -> LightsView:
    """Read the bridge of the signed-in account."""
    return await lights_service.read_lights(user.id)


@router.post(
    "/light",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set one lamp (on, brightness, colour or temperature)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_light(change: LightChange, user: _Account) -> None:
    """Set one lamp."""
    await lights_service.change_light(user.id, change)


@router.post(
    "/room",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set every light of one room (on, brightness)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_room(change: RoomChange, user: _Account) -> None:
    """Set one room."""
    await lights_service.change_room(user.id, change)


@router.post(
    "/scene",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Show one scene",
    dependencies=[Depends(rate_limit_write)],
)
async def post_scene(recall: SceneRecall, user: _Account) -> None:
    """Show one scene."""
    await lights_service.recall_scene(user.id, recall)
