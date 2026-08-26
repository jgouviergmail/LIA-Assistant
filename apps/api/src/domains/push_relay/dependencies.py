"""
Wiring of the wake relay: credentials on disk, one client, one service.

The APNs signing key is read from disk once per process and cached. It is read
off the event loop even so — a bind mount or a secrets driver can make a "small
local file" an arbitrarily slow read, and this one sits on the path of every
notification the relay forwards.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from src.core.config import settings
from src.core.constants import RATE_LIMIT_PUSH_RELAY_REGISTER_PER_MINUTE
from src.core.exceptions import raise_feature_disabled
from src.domains.push_relay.service import PushRelayService
from src.infrastructure.external.apns_client import ApnsClient, ApnsCredentials
from src.infrastructure.rate_limiting.ip_limiter import create_ip_rate_limiter

logger = structlog.get_logger(__name__)

_service: PushRelayService | None = None
_lock = asyncio.Lock()

rate_limit_relay_register = create_ip_rate_limiter(
    namespace="push_relay",
    action="register",
    max_calls=RATE_LIMIT_PUSH_RELAY_REGISTER_PER_MINUTE,
)


async def close_push_relay() -> None:
    """Close the relay's connection to Apple.

    Called from the lifespan shutdown. The APNs client is held open across
    notifications on Apple's own recommendation, so something has to own its
    teardown — an unclosed transport is a test failure in this repository, and
    a leaked socket in production.
    """
    global _service
    if _service is None:
        return
    try:
        await _service.aclose()
    except Exception as exc:
        # Best-effort by nature: the process is going away, and a failure to
        # close is worth a line rather than a raise that would skip the
        # teardown steps queued behind it. Swallowed HERE, next to the resource
        # that owns it, instead of in the shutdown sequence — which is a long
        # list of such steps and should not grow a branch per subsystem.
        logger.warning("push_relay_close_failed", error=str(exc))
    finally:
        _service = None


async def get_push_relay_service() -> PushRelayService:
    """
    Resolve the relay service, building it on first use.

    Returns:
        The process-wide service.

    Raises:
        FeatureDisabledError: When this deployment does not operate a relay.
            Settings validation guarantees that an enabled relay is fully
            configured, so there is no half-configured case to handle here.
    """
    if not settings.push_relay_enabled:
        raise_feature_disabled("push_relay")

    global _service
    if _service is not None:
        return _service

    async with _lock:
        if _service is None:
            key_pem = await asyncio.to_thread(
                Path(str(settings.apns_key_path)).read_text, encoding="utf-8"
            )
            credentials = ApnsCredentials(
                key_pem=key_pem,
                key_id=str(settings.apns_key_id),
                team_id=str(settings.apns_team_id),
                topic=str(settings.apns_topic),
                sandbox=settings.apns_use_sandbox,
            )
            _service = PushRelayService(
                seal_key=str(settings.push_relay_seal_key),
                apns_client=ApnsClient(credentials),
                handle_max_age_days=settings.push_relay_handle_max_age_days,
            )
            logger.info("push_relay_service_ready", topic=settings.apns_topic)
    return _service
