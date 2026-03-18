"""
Custom middleware for FastAPI application.
Includes request ID tracking, CORS, logging, and observability.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import settings
from src.core.constants import GEOIP_COUNTRY_LOCAL
from src.infrastructure.observability.geoip import geoip_resolver
from src.infrastructure.observability.metrics import http_requests_by_country_total

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add unique request ID to each request.
    The request ID is propagated through logs and traces for correlation.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind request ID to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        # Add request ID to request state for access in routes
        request.state.request_id = request_id

        # Process request
        response: Response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

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

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # HSTS — force HTTPS for 1 year, include subdomains (production only)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # CSP — restrict resource loading to known origins
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
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # COOP/COEP for WASM SharedArrayBuffer (Sherpa-onnx KWS multi-threading)
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log HTTP requests and responses with timing.

    Configurable via settings:
    - http_log_level: Log level for successful requests (default: DEBUG)
    - http_log_exclude_paths: Paths to exclude from logging (e.g., /metrics, /health)

    Error responses are always logged at ERROR level for debugging.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start_time = time.time()
        path = request.url.path

        def _is_excluded(req_path: str) -> bool:
            """
            Check if request path matches any excluded path (exact, trailing slash, or subpath).

            Handles common variants like "/health", "/health/", "/healthz" (if explicitly listed),
            and subroutes such as "/metrics/prometheus".
            """
            # Normalize trailing slash for comparison
            normalized = req_path.rstrip("/") or "/"
            for excluded in settings.http_log_exclude_paths:
                excluded_norm = excluded.rstrip("/") or "/"
                if normalized == excluded_norm:
                    return True
                if normalized.startswith(excluded_norm + "/"):
                    return True
            return False

        # Check if path should be excluded from logging
        should_log = not _is_excluded(path)

        # GeoIP enrichment — resolve client IP to geographic data
        # Skipped for excluded paths (/metrics, /health) to avoid overhead
        client_ip = request.client.host if request.client else None
        if should_log:
            geo = geoip_resolver.resolve(client_ip) if client_ip else None

            if geo:
                structlog.contextvars.bind_contextvars(
                    geo_country=geo.country,
                    geo_city=geo.city or "",
                    geo_lat=geo.latitude,
                    geo_lon=geo.longitude,
                )
            elif client_ip:
                structlog.contextvars.bind_contextvars(geo_country=GEOIP_COUNTRY_LOCAL)

            country = geo.country if geo else GEOIP_COUNTRY_LOCAL
            http_requests_by_country_total.labels(country=country).inc()
        # Excluded paths (/metrics, /health) are NOT counted in GeoIP metric
        # to avoid pollution from Prometheus scrapes and health probes

        # Determine log level from settings
        log_level = settings.http_log_level.upper()

        # Log request (if not excluded)
        if should_log:
            log_method = getattr(logger, log_level.lower(), logger.debug)
            log_method(
                "request_started",
                path=path,
                method=request.method,
                client_host=request.client.host if request.client else None,
            )

        try:
            response: Response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response (if not excluded)
            if should_log:
                log_method = getattr(logger, log_level.lower(), logger.debug)
                log_method(
                    "request_completed",
                    path=path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                )

            return response

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000

            # Always log errors at ERROR level, regardless of exclusion
            logger.error(
                "request_failed",
                path=path,
                method=request.method,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
                exc_info=True,
            )
            raise


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Global error handler middleware.
    Catches unhandled exceptions and returns structured error responses.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            response: Response = await call_next(request)
            return response
        except Exception as exc:
            logger.exception(
                "unhandled_exception",
                error=str(exc),
                path=request.url.path,
                method=request.method,
            )

            # Return structured error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc) if settings.debug else "An unexpected error occurred",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )


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
