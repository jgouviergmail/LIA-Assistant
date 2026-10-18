"""Explicit transfer routes authenticate on a detached, short-lived session."""

from uuid import UUID

from fastapi import APIRouter, Depends

from src.core.config import settings
from src.core.exceptions import ValidationError
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.capability_contracts import (
    CapabilityPreviewRequest,
    CapabilitySendRequest,
    CapabilityTransferView,
)
from src.domains.peers.capability_flow import (
    get_capability_transfer,
    preview_capability,
    send_capability,
)
from src.domains.peers.capability_notifications import deliver_capability_receipt
from src.domains.users.models import User

router = APIRouter(
    prefix="/peers/capability-transfers",
    tags=["Peers"],
    dependencies=capability_dependencies(PlatformCapability.PEERS),
)

_limit_transfer = create_user_rate_limiter(
    "peer_capability_transfer",
    settings.peers_capability_rate_limit_calls,
    settings.peers_capability_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)


@router.post(
    "/preview",
    response_model=CapabilityTransferView,
    dependencies=[Depends(_limit_transfer)],
)
async def preview_transfer(
    payload: CapabilityPreviewRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> CapabilityTransferView:
    try:
        return await preview_capability(user.id, payload)
    except ValueError, OSError:
        raise ValidationError("peers_capability_not_shareable") from None


@router.post(
    "/{transfer_id}/send",
    response_model=CapabilityTransferView,
    dependencies=[Depends(_limit_transfer)],
)
async def send_transfer(
    transfer_id: UUID,
    payload: CapabilitySendRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> CapabilityTransferView:
    try:
        receipt = await send_capability(user.id, transfer_id, payload.expected_digest)
        await deliver_capability_receipt(receipt.id)
        return receipt
    except ValueError, OSError:
        raise ValidationError("peers_capability_not_shareable") from None


@router.get("/{transfer_id}", response_model=CapabilityTransferView)
async def read_transfer(
    transfer_id: UUID, user: User = Depends(get_current_active_session_for_stream)
) -> CapabilityTransferView:
    return await get_capability_transfer(user.id, transfer_id)
