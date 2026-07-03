"""
Custom middleware for FastAPI application.
Includes request ID tracking, CORS, logging, and observability.

All custom middleware is implemented as pure ASGI (F28): the historical
``BaseHTTPMiddleware`` versions each spawned an anyio task-group plus memory
streams per request and re-wrapped every SSE chunk, a systematic overhead on
all requests. Pure ASGI runs in the caller's task (contextvars behave
naturally) and is transparent for streaming responses. Execution order is
unchanged: RequestID → SecurityHeaders → Logging → ErrorHandler → routes.
"""

import time
import uuid
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.config import settings
from src.core.constants import GEOIP_COUNTRY_LOCAL
from src.infrastructure.observability.geoip import geoip_resolver
from src.infrastructure.observability.metrics import http_requests_by_country_total

logger = structlog.get_logger(__name__)


class RequestIDMiddleware:
    """
    Pure-ASGI middleware adding a unique request ID to each request.
    The request ID is propagated through logs and traces for correlation.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind request ID to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=scope.get("path", ""),
            method=scope.get("method", ""),
        )

        # Expose to routes via request.state.request_id (Starlette reads
        # request.state from scope["state"])
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class SecurityHeadersMiddleware:
    """
    Pure-ASGI middleware adding security headers to all responses.

    Headers added:
    - X-Frame-Options: DENY - Prevents clickjacking attacks
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-XSS-Protection: 1; mode=block - Enables XSS filter in legacy browsers
    - Strict-Transport-Security - Forces HTTPS for 1 year (production only)
    - Content-Security-Policy - Restricts resource loading origins
    - Cross-Origin-Embedder-Policy: require-corp - Required for SharedArrayBuffer (WASM)
    - Cross-Origin-Opener-Policy: same-origin - Required for SharedArrayBuffer (WASM)

    Note: COOP/COEP headers are required for Sherpa-onnx WASM KWS multi-threading.
    OAuth uses redirect flow (not popups), so COOP won't break authentication.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # CSP — restrict resource loading to known origins.
        # 'unsafe-inline' for styles is required by many UI frameworks;
        # script-src is strict (self only) to prevent XSS.
        csp_directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' https: data: blob:",
            "font-src 'self' data:",
            "connect-src 'self' wss: https:",
            "media-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        self._csp = "; ".join(csp_directives)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Frame-Options"] = "DENY"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-XSS-Protection"] = "1; mode=block"
                # HSTS — force HTTPS for 1 year, include subdomains (production only)
                if settings.is_production:
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains; preload"
                    )
                headers["Content-Security-Policy"] = self._csp
                # COOP/COEP for WASM SharedArrayBuffer (Sherpa-onnx KWS multi-threading)
                headers["Cross-Origin-Embedder-Policy"] = "require-corp"
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


def _is_excluded(req_path: str) -> bool:
    """
    Check if request path matches any excluded path (exact, trailing slash, or subpath).

    Handles common variants like "/health", "/health/", "/healthz" (if explicitly listed),
    and subroutes such as "/metrics/prometheus".
    """
    normalized = req_path.rstrip("/") or "/"
    for excluded in settings.http_log_exclude_paths:
        excluded_norm = excluded.rstrip("/") or "/"
        if normalized == excluded_norm:
            return True
        if normalized.startswith(excluded_norm + "/"):
            return True
    return False


class LoggingMiddleware:
    """
    Pure-ASGI middleware logging HTTP requests and responses with timing.

    Configurable via settings:
    - http_log_level: Log level for successful requests (default: DEBUG)
    - http_log_exclude_paths: Paths to exclude from logging (e.g., /metrics, /health)

    Error responses are always logged at ERROR level for debugging.

    Note: ``duration_ms`` is measured up to ``http.response.start`` — for
    streaming (SSE) responses this is time-to-first-byte, matching the
    historical BaseHTTPMiddleware behaviour (call_next returned at response
    start).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        path = scope.get("path", "")
        method = scope.get("method", "")
        client = scope.get("client")
        client_host: str | None = client[0] if client else None

        should_log = not _is_excluded(path)

        # GeoIP enrichment — resolve client IP to geographic data.
        # Skipped for excluded paths (/metrics, /health) to avoid overhead;
        # excluded paths are also NOT counted in the GeoIP metric (avoids
        # pollution from Prometheus scrapes and health probes).
        if should_log:
            geo = geoip_resolver.resolve(client_host) if client_host else None

            if geo:
                structlog.contextvars.bind_contextvars(
                    geo_country=geo.country,
                    geo_city=geo.city or "",
                    geo_lat=geo.latitude,
                    geo_lon=geo.longitude,
                )
            elif client_host:
                structlog.contextvars.bind_contextvars(geo_country=GEOIP_COUNTRY_LOCAL)

            country = geo.country if geo else GEOIP_COUNTRY_LOCAL
            http_requests_by_country_total.labels(country=country).inc()

        log_level = settings.http_log_level.upper()

        if should_log:
            log_method = getattr(logger, log_level.lower(), logger.debug)
            log_method(
                "request_started",
                path=path,
                method=method,
                client_host=client_host,
            )

        async def send_with_completion_log(message: Message) -> None:
            if message["type"] == "http.response.start" and should_log:
                duration_ms = (time.time() - start_time) * 1000
                log_method = getattr(logger, log_level.lower(), logger.debug)
                log_method(
                    "request_completed",
                    path=path,
                    method=method,
                    status_code=message["status"],
                    duration_ms=round(duration_ms, 2),
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_completion_log)
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            # Always log errors at ERROR level, regardless of exclusion
            logger.error(
                "request_failed",
                path=path,
                method=method,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
                exc_info=True,
            )
            raise


class ErrorHandlerMiddleware:
    """
    Pure-ASGI global error handler middleware.
    Catches unhandled exceptions and returns structured error responses.

    If the response has already started (e.g. mid-stream SSE failure), the
    exception is re-raised: headers are on the wire, a JSON 500 body cannot
    be sent anymore (same limitation the BaseHTTPMiddleware version had).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception as exc:
            logger.exception(
                "unhandled_exception",
                error=str(exc),
                path=scope.get("path", ""),
                method=scope.get("method", ""),
            )

            if response_started:
                raise

            state: dict[str, Any] = scope.get("state") or {}
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc) if settings.debug else "An unexpected error occurred",
                    "request_id": state.get("request_id"),
                },
            )
            await response(scope, receive, send)


def setup_middleware(app: FastAPI) -> None:
    """
    Configure all middleware for the application.

    Args:
        app: FastAPI application instance
    """
    # CORS middleware with restricted methods and headers (security hardening)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "Accept",
            "Accept-Language",
        ],
        expose_headers=["X-Request-ID"],
    )

    # Custom middleware (order matters - applied in reverse)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    logger.info(
        "middleware_configured",
        cors_origins=settings.cors_origins,
    )
