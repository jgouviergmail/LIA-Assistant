"""
System Settings Public API Router.

Provides authenticated (non-admin) read-only endpoints for system settings.
All endpoints require active user authentication.

Endpoints:
- GET /system-settings/debug-panel-status - Get debug panel enabled status
"""

import structlog
from fastapi import APIRouter, Depends

from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.system_settings.schemas import DebugPanelStatusResponse
from src.domains.system_settings.service import (
    get_debug_panel_enabled,
    get_debug_panel_user_access_enabled,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/system-settings",
    tags=["system-settings"],
)


@router.get(
    "/debug-panel-status",
    response_model=DebugPanelStatusResponse,
    summary="Get debug panel status",
    description="Get whether the debug panel is currently enabled for this user. Authenticated users only.",
)
async def get_debug_panel_status(
    current_user: User = Depends(get_current_active_session),
) -> DebugPanelStatusResponse:
    """
    Get debug panel enabled status (read-only).

    Logic:
    - Admin: enabled = system_setting.debug_panel_enabled
    - Non-admin: enabled = system_setting.debug_panel_user_access_enabled AND user.debug_panel_enabled

    Also returns user_access_available so the frontend knows whether to show
    the debug panel toggle in user preferences.
    """
    user_access_available = await get_debug_panel_user_access_enabled()

    if current_user.is_superuser:
        # Admin: their debug panel is controlled by the main admin setting
        enabled = await get_debug_panel_enabled()
    else:
        # Non-admin: both admin user-access AND personal preference must be True
        enabled = user_access_available and current_user.debug_panel_enabled

    return DebugPanelStatusResponse(
        enabled=enabled,
        user_access_available=user_access_available,
    )
