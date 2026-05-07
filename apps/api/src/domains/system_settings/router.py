"""
System Settings Admin API Router.

Provides admin-only endpoints for managing application-wide settings.
All endpoints require superuser authentication.

The Voice TTS Mode endpoints lived here until v1.20.x — they were retired
when the TTS provider/model selection moved to ``llm_config_overrides``
(see ADR-081). The voice picker and provider-specific tuning now live in
the Configuration LLM admin (``voice_tts`` LLM type).

Created: 2026-01-16
"""

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_superuser_session
from src.domains.system_settings.schemas import (
    DebugPanelEnabledResponse,
    DebugPanelEnabledUpdate,
    DebugPanelUserAccessResponse,
    DebugPanelUserAccessUpdate,
)
from src.domains.system_settings.service import SystemSettingsService
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/system-settings",
    tags=["admin", "system-settings"],
    dependencies=[Depends(get_current_superuser_session)],
)


# =============================================================================
# DEBUG PANEL SETTINGS
# =============================================================================


@router.get(
    "/debug-panel",
    response_model=DebugPanelEnabledResponse,
    summary="Get debug panel enabled status",
    description="Get whether the debug panel is enabled. Admin only.",
)
async def get_debug_panel_enabled(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> DebugPanelEnabledResponse:
    """
    Get current debug panel enabled status.

    Returns whether the debug panel is enabled and metadata including
    who last changed it and when.
    """
    service = SystemSettingsService(db)
    return await service.get_debug_panel_enabled()


@router.put(
    "/debug-panel",
    response_model=DebugPanelEnabledResponse,
    summary="Update debug panel enabled status",
    description="Enable or disable the debug panel. Admin only.",
)
async def update_debug_panel_enabled(
    update: DebugPanelEnabledUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> DebugPanelEnabledResponse:
    """
    Update debug panel enabled status.

    Enables or disables the debug panel for all users immediately.

    An audit log is created for this change.
    """
    logger.info(
        "debug_panel_enabled_update_requested",
        admin_user_id=str(current_user.id),
        new_value=update.enabled,
        change_reason=update.change_reason,
    )

    service = SystemSettingsService(db)
    return await service.set_debug_panel_enabled(
        update=update,
        admin_user_id=current_user.id,
        request=request,
    )


# =============================================================================
# DEBUG PANEL USER ACCESS SETTINGS
# =============================================================================


@router.get(
    "/debug-panel-user-access",
    response_model=DebugPanelUserAccessResponse,
    summary="Get debug panel user access status",
    description="Get whether non-admin users can toggle their own debug panel. Admin only.",
)
async def get_debug_panel_user_access(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> DebugPanelUserAccessResponse:
    """
    Get current debug panel user access status.

    Returns whether non-admin users are allowed to toggle their own
    debug panel in their preferences settings.
    """
    service = SystemSettingsService(db)
    return await service.get_debug_panel_user_access()


@router.put(
    "/debug-panel-user-access",
    response_model=DebugPanelUserAccessResponse,
    summary="Update debug panel user access status",
    description="Enable or disable non-admin users' ability to toggle their own debug panel. Admin only.",
)
async def update_debug_panel_user_access(
    update: DebugPanelUserAccessUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> DebugPanelUserAccessResponse:
    """
    Update debug panel user access status.

    When enabled, non-admin users see a "Debug Panel" section in their
    Preferences with their own on/off toggle.
    When disabled, non-admin users lose access to the debug panel
    regardless of their personal preference.

    An audit log is created for this change.
    """
    logger.info(
        "debug_panel_user_access_update_requested",
        admin_user_id=str(current_user.id),
        new_value=update.available,
        change_reason=update.change_reason,
    )

    service = SystemSettingsService(db)
    return await service.set_debug_panel_user_access(
        update=update,
        admin_user_id=current_user.id,
        request=request,
    )
