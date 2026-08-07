"""Admin API for the platform capability switches.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_superuser_session
from src.domains.feature_switches.admin_service import CapabilitySwitchAdminService
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.feature_switches.schemas import (
    CapabilitySwitchResponse,
    CapabilitySwitchUpdate,
)
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/capabilities",
    tags=["admin", "capabilities"],
    dependencies=[Depends(get_current_superuser_session)],
)


@router.get(
    "",
    response_model=list[CapabilitySwitchResponse],
    summary="List the platform capability switches",
    description=(
        "List every administrable capability with its operator switch, the "
        "deployment ceiling, and what the runtime actually enforces. Admin only."
    ),
)
async def list_capability_switches(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> list[CapabilitySwitchResponse]:
    """List every capability switch and its effective state."""
    service = CapabilitySwitchAdminService(db)
    return await service.list_switches()


@router.put(
    "/{capability}",
    response_model=CapabilitySwitchResponse,
    summary="Turn one capability on or off",
    description=(
        "Flip one capability switch. Turning it on only lifts the operator's "
        "own restriction: a deployment that forbids the capability keeps it "
        "unavailable. Admin only."
    ),
)
async def update_capability_switch(
    capability: PlatformCapability,
    update: CapabilitySwitchUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> CapabilitySwitchResponse:
    """Flip one capability switch.

    The path parameter is the closed enum, so an unknown capability is
    rejected by FastAPI at the boundary rather than silently creating a
    setting nobody reads.
    """
    logger.info(
        "capability_switch_update_requested",
        capability=capability.value,
        enabled=update.enabled,
        admin_user_id=str(current_user.id),
    )
    service = CapabilitySwitchAdminService(db)
    return await service.set_switch(
        capability=capability,
        update=update,
        admin_user_id=current_user.id,
        request=request,
    )
