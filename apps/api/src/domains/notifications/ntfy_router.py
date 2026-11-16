"""The ntfy settings of an account (ADR-391).

Guarded by the ``ntfy`` capability: switched off, the routes refuse and nothing is published —
the subscriptions stay (a switch removes the ability, never the record, ADR-280).

A topic is a password and a token a credential: the routes are private input routes — a
refusal never reflects what was typed, an answer is never cached.

A test publication is a request to a server: the route ends its read transaction before it
publishes (ADR-304), and a per-account limit keeps a click from hammering a shared server.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RATE_LIMIT_NTFY_TEST_PER_MINUTE
from src.core.dependencies import get_db
from src.core.i18n import _, resolve_language
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.notifications.ntfy_delivery import NtfyNotice, click_url, deliver
from src.domains.notifications.ntfy_schemas import (
    NtfyOverview,
    NtfyQrCode,
    NtfySubscriptionCreate,
    NtfySubscriptionUpdate,
    NtfySubscriptionView,
    NtfyTestResult,
)
from src.domains.notifications.ntfy_service import NtfySubscriptionService
from src.domains.users.models import User
from src.infrastructure.rate_limiting.user_limiter import create_user_rate_limiter
from src.infrastructure.utils.qr_code import render_qr_data_uri

router = APIRouter(
    prefix="/notifications/ntfy",
    tags=["notifications"],
    dependencies=capability_dependencies(PlatformCapability.NTFY),
    route_class=PrivateApplicationInputRoute,
)

rate_limit_ntfy_test = create_user_rate_limiter(
    "ntfy_test", max_calls=RATE_LIMIT_NTFY_TEST_PER_MINUTE, window_seconds=60
)


@router.get("", response_model=NtfyOverview, summary="The account's ntfy settings")
async def ntfy_overview(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NtfyOverview:
    """The instance server, the rules and the account's subscriptions."""
    return await NtfySubscriptionService(db).overview(current_user.id)


@router.post(
    "",
    response_model=NtfySubscriptionView,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe a topic",
)
async def create_ntfy_subscription(
    request: NtfySubscriptionCreate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NtfySubscriptionView:
    """Make a subscription on the instance's server or on a public one."""
    view = await NtfySubscriptionService(db).create(current_user.id, request)
    await db.commit()
    return view


@router.patch(
    "/{subscription_id}", response_model=NtfySubscriptionView, summary="Change a subscription"
)
async def update_ntfy_subscription(
    subscription_id: UUID,
    request: NtfySubscriptionUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NtfySubscriptionView:
    """Change what a subscription receives, or pause it."""
    view = await NtfySubscriptionService(db).update(current_user.id, subscription_id, request)
    await db.commit()
    return view


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a subscription",
)
async def delete_ntfy_subscription(
    subscription_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a subscription."""
    await NtfySubscriptionService(db).delete(current_user.id, subscription_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{subscription_id}/qr",
    response_model=NtfyQrCode,
    summary="The QR code that subscribes a device",
)
async def ntfy_subscription_qr(
    subscription_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NtfyQrCode:
    """Draw the QR code a phone scans to subscribe the ntfy app to one subscription."""
    text = await NtfySubscriptionService(db).subscribe_target(current_user.id, subscription_id)
    # The read ends before the drawing, which is CPU-bound and runs off the event loop.
    await db.commit()
    return NtfyQrCode(qr_data_uri=await asyncio.to_thread(render_qr_data_uri, text))


@router.post(
    "/{subscription_id}/test",
    response_model=NtfyTestResult,
    summary="Send a test notification",
    dependencies=[Depends(rate_limit_ntfy_test)],
)
async def test_ntfy_subscription(
    subscription_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NtfyTestResult:
    """Publish a test notification to one subscription, as its content choice shows it.

    The person asked for this one subscription: it is tested even while paused.
    """
    target = await NtfySubscriptionService(db).target(current_user.id, subscription_id)
    language = resolve_language(current_user.language)
    notice = NtfyNotice(
        title=_("LIA test notification", language),
        body=_("ntfy works: LIA can reach you here.", language),
        click=click_url(None),
        language=language,
    )
    # The read ends here: no transaction stays open while the server answers (ADR-304).
    await db.commit()
    (outcome,) = (await deliver([(target, notice)])).outcomes
    return NtfyTestResult(outcome=outcome)


__all__ = ["router"]
