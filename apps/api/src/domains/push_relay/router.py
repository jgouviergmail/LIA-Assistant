"""
Wake relay endpoints.

Neither is authenticated, and both are bounded instead.

Registration cannot be: the shell holds no account with the relay, only with
its own server. What protects it is that a handle is only useful for the device
that presented its token — minting one for a device you already control buys
nothing. A per-IP window bounds the noise.

Waking is authenticated BY the handle: holding it is the whole permission, and
that permission extends to exactly one thing — a fixed, contentless
notification to one device. The budget is per handle, so a leaked one cannot
spend anyone else's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.core.constants import RATE_LIMIT_PUSH_RELAY_WAKE_PER_MINUTE
from src.core.exceptions import raise_rate_limit_exceeded
from src.domains.push_relay.dependencies import (
    get_push_relay_service,
    rate_limit_relay_register,
)
from src.domains.push_relay.schemas import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    WakeRequest,
    WakeResponse,
)
from src.domains.push_relay.service import PushRelayService, WakeOutcome

router = APIRouter(prefix="/push-relay", tags=["push-relay"])

# The two outcomes a caller can never recover from by retrying. Everything else
# — including Apple being down and this relay being misconfigured — leaves the
# handle valid, and deleting it there would cost a user their notifications
# over an incident of ours.
_FORGETTABLE = frozenset({WakeOutcome.UNKNOWN_HANDLE, WakeOutcome.DEVICE_GONE})


@router.post(
    "/devices",
    response_model=DeviceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a device with the relay",
    description=(
        "Exchange an APNs device token for an opaque handle. The relay stores "
        "nothing: the handle carries the device token, sealed."
    ),
)
async def register_device(
    request: DeviceRegisterRequest,
    _rate_limit: None = Depends(rate_limit_relay_register),
    service: PushRelayService = Depends(get_push_relay_service),
) -> DeviceRegisterResponse:
    """
    Register a device and return its handle.

    Args:
        request: The device token, its gateway, and the language the generic
            wake text should be written in.
        _rate_limit: Per-IP throttle.
        service: The relay service.

    Returns:
        The handle, which the shell then reports to its own LIA server.
    """
    handle = await service.register(
        request.device_token,
        sandbox=request.sandbox,
        language=request.normalized_language(),
    )
    return DeviceRegisterResponse(handle=handle)


@router.post(
    "/wake",
    response_model=WakeResponse,
    status_code=status.HTTP_200_OK,
    summary="Wake a device",
    description=(
        "Send the fixed, contentless notification to the device a handle names. "
        "The relay never carries what the notification is about."
    ),
)
async def wake_device(
    request: WakeRequest,
    service: PushRelayService = Depends(get_push_relay_service),
) -> WakeResponse:
    """
    Spend a handle.

    A well-formed call that reaches Apple is a successful call, whatever Apple
    then said — so the outcome travels in the body rather than as a status
    code. The one exception is throttling, where 429 plus ``Retry-After`` is
    what an HTTP client already knows how to obey.

    Args:
        request: The handle to spend.
        service: The relay service.

    Returns:
        The outcome, and whether the caller should delete its handle.

    Raises:
        RateLimitError: When this handle's budget is spent.
    """
    outcome = await service.wake(request.handle)

    if outcome is WakeOutcome.THROTTLED:
        raise_rate_limit_exceeded(
            limit=RATE_LIMIT_PUSH_RELAY_WAKE_PER_MINUTE,
            window_seconds=60,
            retry_after=60,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many wakes for this device. Please try again later.",
                "retry_after_seconds": 60,
            },
            headers={"Retry-After": "60"},
        )

    return WakeResponse(
        outcome=outcome,
        should_forget_handle=outcome in _FORGETTABLE,
    )
