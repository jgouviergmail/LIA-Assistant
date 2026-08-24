"""
The wake relay's business logic: issue handles, and spend them.

Two invariants live here and nowhere else.

The first is honesty about delivery. Apple accepting a notification is the only
outcome reported as success, and the four ways a wake can fail stay
distinguishable — because a calling server does something different with each:
delete the handle, drop it and stop, back off, or wait for us to fix ourselves.
Collapsing them is how a dead token gets pushed to forever, or a live one gets
deleted over a misconfiguration of ours.

The second is that the relay carries no content. The payload is assembled from
a fixed table and the language sealed in the handle, and there is no path by
which a caller can influence a single byte of it. That is the entire argument
for the relay being acceptable at all.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import timedelta
from enum import StrEnum
from typing import Any, cast

import structlog

from src.core.constants import (
    PUSH_RELAY_WAKE_COLLAPSE_ID,
    RATE_LIMIT_PUSH_RELAY_WAKE_PER_MINUTE,
)
from src.core.i18n_push_relay import PushRelayMessages
from src.core.i18n_types import SupportedLanguage
from src.domains.push_relay.seal import seal_device, unseal_handle
from src.infrastructure.external.apns_client import ApnsClient, ApnsDeliveryStatus
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


class WakeOutcome(StrEnum):
    """What happened to one wake, in the terms a calling server acts on.

    Attributes:
        SENT: Apple took custody. Not a claim the phone displayed anything.
        UNKNOWN_HANDLE: Forged, tampered with, or older than the window. The
            caller should delete it — retrying can never start working.
        DEVICE_GONE: Apple says the device no longer runs the app. The caller
            should delete it too, but for a reason worth distinguishing.
        THROTTLED: This handle's budget is spent.
        UNAVAILABLE: Apple is unreachable or busy. Worth retrying.
        MISCONFIGURED: Apple refused for a reason that is ours. The caller must
            keep its handle: nothing about the device is wrong.
    """

    SENT = "sent"
    UNKNOWN_HANDLE = "unknown_handle"
    DEVICE_GONE = "device_gone"
    THROTTLED = "throttled"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"


#: Every verdict Apple can produce, mapped to what a calling server does about
#: it. Completeness is asserted at boot (ADR-085 pattern) rather than left to a
#: KeyError on the hot path: a new APNs status added without a decision here
#: would raise mid-wake, on a device whose owner is waiting.
_OUTCOME_BY_STATUS: dict[ApnsDeliveryStatus, WakeOutcome] = {
    ApnsDeliveryStatus.ACCEPTED: WakeOutcome.SENT,
    ApnsDeliveryStatus.DEVICE_GONE: WakeOutcome.DEVICE_GONE,
    ApnsDeliveryStatus.UNAVAILABLE: WakeOutcome.UNAVAILABLE,
    ApnsDeliveryStatus.REJECTED: WakeOutcome.MISCONFIGURED,
}


def assert_wake_outcome_completeness() -> None:
    """Refuse to boot if an APNs verdict has no decision attached.

    Called at MODULE SCOPE, below, rather than from ``run_failfast_validations``.
    Importing this module is exactly when the map becomes live: the router is
    included only on a deployment that operates a relay, and that inclusion is
    what imports this. So the app refuses to boot precisely where the invariant
    matters, and nowhere else pays for a subsystem it does not run.

    Raises:
        AssertionError: If any ``ApnsDeliveryStatus`` is unmapped.
    """
    missing = {s for s in ApnsDeliveryStatus if s not in _OUTCOME_BY_STATUS}
    if missing:
        names = ", ".join(sorted(s.value for s in missing))
        raise AssertionError(
            f"_OUTCOME_BY_STATUS is missing {len(missing)} ApnsDeliveryStatus "
            f"value(s): {names}. Every verdict Apple can return must say whether "
            "the caller keeps its handle, drops it, or retries — see "
            "src/domains/push_relay/service.py."
        )


class PushRelayService:
    """Issue device handles and spend them against Apple."""

    def __init__(
        self,
        *,
        seal_key: str,
        apns_client: ApnsClient,
        handle_max_age_days: int,
        limiter_factory: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            seal_key: Fernet key sealing and reading handles.
            apns_client: The provider client. Injected so the service can be
                tested without a signing key or a network.
            handle_max_age_days: Age past which a handle is refused.
            limiter_factory: Resolver for the shared Redis limiter.
        """
        self._seal_key = seal_key
        self._apns = apns_client
        self._max_age = timedelta(days=handle_max_age_days)
        self._limiter_factory = limiter_factory or get_rate_limiter

    async def register(
        self,
        device_token: str,
        *,
        sandbox: bool,
        language: str,
    ) -> str:
        """
        Turn a device token into a handle a third-party server may hold.

        Args:
            device_token: The APNs device token reported by the shell.
            sandbox: Whether it belongs to Apple's development gateway.
            language: Language of the generic wake text, sealed alongside.

        Returns:
            The handle. Nothing is stored: it IS the record.
        """
        handle = seal_device(
            device_token,
            sandbox=sandbox,
            key=self._seal_key,
            language=language,
        )
        logger.info("push_relay_device_registered", sandbox=sandbox)
        return handle

    async def wake(self, handle: str) -> WakeOutcome:
        """
        Send the generic notification to the device a handle names.

        Args:
            handle: The handle presented by a calling server.

        Returns:
            The outcome, in the terms the caller acts on. This never raises:
            a server deciding whether to keep a handle needs an answer.
        """
        device = unseal_handle(handle, key=self._seal_key, max_age=self._max_age)
        if device is None:
            logger.info("push_relay_wake_refused", reason="unknown_handle")
            return WakeOutcome.UNKNOWN_HANDLE

        if not await self._within_budget(handle):
            logger.warning("push_relay_wake_throttled")
            return WakeOutcome.THROTTLED

        language = cast(SupportedLanguage, device.language)
        payload = {
            "aps": {
                "alert": {
                    "title": PushRelayMessages.wake_title(language),
                    "body": PushRelayMessages.wake_body(language),
                },
            }
        }

        result = await self._apns.send(
            device.device_token,
            payload,
            collapse_id=PUSH_RELAY_WAKE_COLLAPSE_ID,
            sandbox=device.sandbox,
        )
        outcome = _OUTCOME_BY_STATUS[result.status]
        logger.info(
            "push_relay_wake_completed",
            outcome=outcome.value,
            apns_reason=result.reason,
        )
        return outcome

    async def aclose(self) -> None:
        """Release the connection this service holds to Apple."""
        await self._apns.aclose()

    async def _within_budget(self, handle: str) -> bool:
        """Check this handle's own wake budget.

        The window is keyed on the handle rather than the caller's address: one
        self-hosted server legitimately wakes many devices from one address, and
        one leaked handle must not be able to spend everyone else's budget.

        Args:
            handle: The presented handle.

        Returns:
            Whether the wake may proceed. Fails open — the limiter being
            unreachable must not silence every notification on the platform.
        """
        # The handle is a bearer capability: hashed, it can key a counter and
        # appear in a log without being usable by whoever reads it.
        digest = hashlib.sha256(handle.encode()).hexdigest()[:32]
        try:
            limiter = await self._limiter_factory()
            return bool(
                await limiter.acquire(
                    key=f"push_relay:wake:{digest}",
                    max_calls=RATE_LIMIT_PUSH_RELAY_WAKE_PER_MINUTE,
                    window_seconds=60,
                )
            )
        except Exception as exc:
            logger.error("push_relay_budget_check_failed", error=str(exc))
            return True


# The map is live from the moment this module exists. Asserting here means a
# missing verdict is an ImportError at boot rather than a KeyError mid-wake, on
# a device whose owner is waiting (ADR-085 completeness doctrine).
assert_wake_outcome_completeness()
