"""
Client for a wake relay, from a self-hosted deployment's side.

This is how a server that cannot reach the published iOS app asks the
deployment that can. It sends one opaque handle and nothing else: no user, no
content, no reason.

The governing rule is that **doubt never deletes**. A relay that is unreachable,
overloaded, misrouted, or answering something this client does not recognise
yields "not sent, keep the handle". Only an explicit ``should_forget_handle``
may cost a user their notifications — because keeping a dead handle wastes one
HTTP call per notification, while dropping a live one silences a phone until
its owner next opens the app.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

_WAKE_PATH = "/api/v1/push-relay/wake"


@dataclass(frozen=True, slots=True)
class RelayWakeResult:
    """What one wake achieved, and what to do with the handle afterwards."""

    sent: bool
    should_forget_handle: bool
    error: str | None = None


class PushRelayClient:
    """Ask a relay to wake one device."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Initialize the client.

        Args:
            base_url: Base URL of the relay, with or without a trailing slash.
            timeout: Per-request timeout in seconds.
            transport: Injected transport, for tests.
        """
        self._url = base_url.rstrip("/") + _WAKE_PATH
        self._timeout = timeout
        self._transport = transport

    async def wake(self, handle: str) -> RelayWakeResult:
        """
        Ask the relay to wake the device a handle names.

        Args:
            handle: The opaque handle this server stored for the device.

        Returns:
            Whether the notification was sent, and whether the handle should be
            dropped. Never raises: a caller iterating over a user's devices
            needs an answer per device, not an exception that ends the loop.
        """
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as client:
                response = await client.post(self._url, json={"handle": handle})
        except httpx.HTTPError as exc:
            logger.warning("push_relay_unreachable", error=str(exc))
            return RelayWakeResult(sent=False, should_forget_handle=False, error=type(exc).__name__)

        if not response.is_success:
            logger.warning("push_relay_refused", status_code=response.status_code)
            return RelayWakeResult(
                sent=False,
                should_forget_handle=False,
                error=f"relay_status_{response.status_code}",
            )

        try:
            body = response.json()
            outcome = body["outcome"]
            forget = body.get("should_forget_handle", False)
        except ValueError, TypeError, KeyError:
            logger.warning("push_relay_answer_unreadable")
            return RelayWakeResult(
                sent=False, should_forget_handle=False, error="relay_answer_unreadable"
            )

        return RelayWakeResult(
            sent=outcome == "sent",
            should_forget_handle=bool(forget),
            error=None if outcome == "sent" else str(outcome),
        )
