"""Pure-ASGI API scan protection excluding normal session and resource errors."""

import hashlib
import uuid
from ipaddress import ip_address

import structlog
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.client_ip import UNKNOWN_CLIENT_IP, resolve_client_ip
from src.core.config import settings
from src.core.constants import RATE_LIMIT_GLOBAL_EXEMPT_PATHS
from src.core.i18n_api_messages import APIMessages
from src.infrastructure.observability.metrics_http_scan import (
    http_scan_bans_total,
    http_scan_blocked_total,
)
from src.infrastructure.rate_limiting.http_scan import RedisHTTPScanGuard, ScanReason

logger = structlog.get_logger(__name__)


def _is_public_client(client_ip: str) -> bool:
    try:
        return ip_address(client_ip).is_global
    except ValueError:
        # The resolver's peer fallback can be a transport-specific name.
        return False


def _candidate_ip(scope: Scope) -> str | None:
    if (
        scope["type"] != "http"
        or not settings.http_scan_protection_enabled
        or scope.get("method") == "OPTIONS"
        or scope.get("path") in RATE_LIMIT_GLOBAL_EXEMPT_PATHS
    ):
        return None
    client_ip = resolve_client_ip(scope)
    if client_ip == UNKNOWN_CLIENT_IP or not _is_public_client(client_ip):
        return None
    return client_ip


def _failure_reason(scope: Scope, status: int) -> ScanReason | None:
    if status == 404 and scope.get("route") is None:
        return "not_found"
    # Resource/session 401s are normal. Only submitted credentials earn strikes.
    credential_paths = {
        f"{settings.api_prefix}/auth/login",
        f"{settings.api_prefix}/auth/mfa/verify",
    }
    if status == 401 and scope.get("method") == "POST" and scope.get("path") in credential_paths:
        return "credentials"
    return None


class ScanProtectionMiddleware:
    """Ban public caller IPs; internal SSR and monitoring cannot be locked out."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.guard = RedisHTTPScanGuard()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        client_ip = _candidate_ip(scope)
        if client_ip is None:
            await self.app(scope, receive, send)
            return
        remaining = await self.guard.remaining(client_ip)
        if remaining:
            http_scan_blocked_total.inc()
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "http_scan_blocked",
                    "message": APIMessages.too_many_requests(),
                    "retry_after": remaining,
                },
                headers={"Retry-After": str(remaining)},
            )
            await response(scope, receive, send)
            return

        started = False

        async def observe_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start" and not started:
                started = True
                reason = _failure_reason(scope, message["status"])
                if reason is not None:
                    # No query, username or body is stored in Redis.
                    fingerprint = (
                        hashlib.sha256(scope.get("path", "").encode()).hexdigest()
                        if reason == "not_found"
                        else uuid.uuid4().hex
                    )
                    if await self.guard.record(client_ip, reason, fingerprint):
                        http_scan_bans_total.labels(reason=reason).inc()
                        logger.warning(
                            "http_scan_ip_banned",
                            client_ip=client_ip,
                            reason=reason,
                            ban_seconds=settings.http_scan_ban_seconds,
                        )
            await send(message)

        await self.app(scope, receive, observe_start)
