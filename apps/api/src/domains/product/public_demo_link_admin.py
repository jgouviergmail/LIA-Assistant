"""The operator's switch over the public demonstrator link.

"Take the demo offline" is the most urgent action an operator can need. It
must be one click away and take effect immediately, so it lives in the audited
settings store rather than in an environment variable that needs a deploy.

The admin view reports one thing the anonymous route deliberately hides:
whether a URL is configured at all. An operator flipping a switch on an
instance that serves no demonstrator must read "nothing to show" rather than
believe a link went live.

Created: 2026-08-06 (live-demonstrator programme, lot 5)
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_superuser_session
from src.domains.product.public_demo_link import (
    configured_public_demo_url,
    resolve_public_demo_link,
)
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.service import write_setting
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/public-demo-link",
    tags=["admin", "product"],
    dependencies=[Depends(get_current_superuser_session)],
)

#: Audit action recorded for every flip of the link.
_AUDIT_ACTION = "public_demo_link_changed"


class PublicDemoLinkAdminView(BaseModel):
    """What an operator sees about the demonstrator link."""

    enabled: bool = Field(description="Whether visitors are currently shown the link")
    url: str | None = Field(default=None, description="Where it points when live; absent otherwise")
    url_configured: bool = Field(
        description=(
            "Whether this deployment declares a demonstrator URL at all. False "
            "means the switch has nothing to show, whatever its position."
        )
    )


class PublicDemoLinkUpdate(BaseModel):
    """Operator decision on the demonstrator link."""

    enabled: bool = Field(description="Show the link to visitors")
    change_reason: str | None = Field(
        default=None, max_length=500, description="Why, for the audit trail"
    )


async def read_admin_view() -> PublicDemoLinkAdminView:
    """Read the link state as an operator needs to see it.

    Returns:
        The visitor-facing state, plus whether a URL is deployed at all.
    """
    link = await resolve_public_demo_link()
    url_configured = bool(configured_public_demo_url())
    return PublicDemoLinkAdminView(
        enabled=link.enabled, url=link.url, url_configured=url_configured
    )


async def set_public_demo_link(
    db: AsyncSession,
    *,
    enabled: bool,
    admin_user_id: UUID,
    request: Request,
    change_reason: str | None = None,
) -> PublicDemoLinkAdminView:
    """Show or hide the demonstrator link, through the audited store.

    Args:
        db: Database session.
        enabled: Whether visitors should be shown the link.
        admin_user_id: Admin making the change.
        request: FastAPI request, for the audit trail.
        change_reason: Optional justification recorded with the change.

    Returns:
        The new state as the operator sees it.
    """
    await write_setting(
        db,
        SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED,
        enabled,
        action=_AUDIT_ACTION,
        admin_user_id=admin_user_id,
        request=request,
        change_reason=change_reason,
    )
    logger.info("public_demo_link_updated", enabled=enabled, admin_user_id=str(admin_user_id))
    return await read_admin_view()


@router.get(
    "",
    response_model=PublicDemoLinkAdminView,
    summary="Read the public demonstrator link state",
    description="Whether visitors see the demonstrator link, and whether one is deployed.",
)
async def get_admin_public_demo_link(
    current_user: User = Depends(get_current_superuser_session),
) -> PublicDemoLinkAdminView:
    """Read the demonstrator link state (admin only)."""
    return await read_admin_view()


@router.put(
    "",
    response_model=PublicDemoLinkAdminView,
    summary="Show or hide the public demonstrator link",
    description=(
        "Flip the link visitors are shown. Takes effect immediately — this is "
        "the control an operator reaches for during an incident."
    ),
)
async def update_admin_public_demo_link(
    update: PublicDemoLinkUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> PublicDemoLinkAdminView:
    """Show or hide the demonstrator link (admin only)."""
    return await set_public_demo_link(
        db,
        enabled=update.enabled,
        admin_user_id=current_user.id,
        request=request,
        change_reason=update.change_reason,
    )
