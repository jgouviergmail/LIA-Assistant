"""Private debug feed for native calls, including calls outside a chat turn."""

import asyncio

from fastapi import APIRouter, Depends, Response

from src.core.exceptions import ExternalServiceError, raise_permission_denied
from src.core.session_dependencies import get_current_active_session
from src.domains.system_settings.debug_access import can_read_debug
from src.domains.users.models import User
from src.infrastructure.llm.jev_debug_models import JevTracePage
from src.infrastructure.llm.jev_debug_store import read_traces

router = APIRouter(prefix="/debug/jev", tags=["llm-debug"])


@router.get("", response_model=JevTracePage)
async def get_jev_calls(
    response: Response, user: User = Depends(get_current_active_session)
) -> JevTracePage:
    """The caller's own diagnostics only; never a selectable user id."""
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(1):
            if await can_read_debug(user):
                return await read_traces(user.id)
    except Exception as exc:
        raise ExternalServiceError(
            "jev_debug", headers={"Cache-Control": "no-store"}, error_type=type(exc).__name__
        ) from None
    raise_permission_denied(action="read", resource_type="debug", user_id=user.id)
