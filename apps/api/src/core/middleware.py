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
from contextlib import suppress
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.client_ip import UNKNOWN_CLIENT_IP, resolve_client_ip
from src.core.config import settings
from src.core.constants import (
    GEOIP_COUNTRY_LOCAL,
    MAX_REQUEST_BODY_EXEMPT_PATHS,
    RATE_LIMIT_GLOBAL_EXEMPT_PATHS,
    RATE_LIMIT_GLOBAL_WINDOW_SECONDS,
)
from src.core.native_client import NATIVE_CLIENT_HEADER
from src.core.rate_limit_config import rate_limiting_enabled
from src.infrastructure.observability.geoip import geoip_resolver
from src.infrastructure.observability.metrics import (
    http_rate_limit_degraded_total,
    http_rate_limit_hits_total,
    http_request_body_rejected_total,
    http_requests_by_country_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

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


class RateLimitMiddleware:
    """Pure-ASGI global HTTP rate limit, actually enforced (SEC-016).

    A ``slowapi.Limiter`` was built with ``default_limits`` and stored on
    ``app.state``, but no middleware or decorator ever consulted it: the limit
    was declared, never applied. Specialised limiters (login, register, export,
    static maps, DevOps, tools) do run, so the exposure was every OTHER route —
    which is most of the 327.

    This is a FLOOD BACKSTOP, not a business rule. Those specialised budgets are
    stricter and stay exactly where they are; this one only stops a single
    client from consuming the whole API. Its ceiling is sized from measurement:
    a real browser session peaked at 67 requests in a minute, so the default of
    300 cannot fire on legitimate use.

    Design decisions worth keeping:

    - **Redis-backed**, via the existing ``RedisRateLimiter`` sliding window. The
      SlowAPI limiter defaulted to in-memory counters, which on four uvicorn
      workers means four independent budgets — a limit four times looser than
      advertised, and inconsistent between requests.
    - **Fail-open** when Redis is unavailable, matching the policy already
      documented for every other limiter in the codebase. On a single-instance
      deployment, failing closed converts a Redis outage into a total outage —
      a self-inflicted denial of service worse than the abuse it prevents. The
      blind window is made visible by ``http_rate_limit_degraded_total``.
    - **Keyed on the client address resolved by ``core.client_ip``**, never on a
      cookie: a cookie-derived key is rotatable by the very client we are trying
      to bound. That chokepoint prefers ``CF-Connecting-IP`` precisely because
      the peer uvicorn resolves is ALSO rotatable — it is rewritten from the
      leftmost ``X-Forwarded-For`` entry, which the visitor writes (ADR-213).
    - **Probes exempt**, or Docker's healthcheck and Prometheus would rate-limit
      the platform's own supervision and read it back as an outage.
    - **SSE is charged once**, at admission. Only the request direction is
      inspected; an accepted stream is never interrupted afterwards.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.max_calls = settings.rate_limit_global_per_minute
        self.window_seconds = RATE_LIMIT_GLOBAL_WINDOW_SECONDS
        self.exempt_paths = RATE_LIMIT_GLOBAL_EXEMPT_PATHS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_subject_to_limit(scope):
            await self.app(scope, receive, send)
            return

        if await self._is_allowed(scope):
            await self.app(scope, receive, send)
            return

        await self._reject(scope, send)

    def _is_subject_to_limit(self, scope: Scope) -> bool:
        """Whether this request is in scope for the global limit.

        The exemption is an EXACT match. A ``startswith`` test exempted every
        path merely BEGINNING with a probe name — ``/healthz``, ``/health-x``,
        ``/metrics-flood`` — so prefixing any request with ``/health`` was
        enough to cross the API with no rate limit applied. Those paths answer
        404, but a 404 still costs a full middleware traversal and routing pass,
        and it is served at whatever rate the client can produce: the ceiling
        this middleware exists to enforce had a trivial bypass.

        Matching exactly costs nothing here — the three exempted probes expose
        no sub-path (``/health`` and ``/ready`` in ``src/api/health.py``,
        ``/metrics`` added in ``main.py``), and the probes that actually poll
        them (Docker's healthcheck, Prometheus, the deploy readiness gate) all
        request the exact form.
        """
        if not rate_limiting_enabled(settings):
            return False
        return scope.get("path", "") not in self.exempt_paths

    @staticmethod
    def _client_key(scope: Scope) -> str:
        """Build the bucket key for a request.

        Resolution goes through the single chokepoint ``resolve_client_ip``,
        which prefers ``CF-Connecting-IP`` — the one address the caller cannot
        author. This used to read the peer address as uvicorn resolved it, which
        looked safe but is not: under ``--forwarded-allow-ips "*"`` uvicorn
        rewrites that peer from the LEFTMOST ``X-Forwarded-For`` entry, i.e. the
        value the visitor supplied (Cloudflare appends, it does not replace).
        Rotating that value therefore minted a fresh budget per request —
        reproduced 2026-08-05.
        """
        return f"http:global:{resolve_client_ip(scope)}"

    async def _is_allowed(self, scope: Scope) -> bool:
        """Consume one token, allowing the request when Redis is unavailable."""
        try:
            limiter = await get_rate_limiter()
            return await limiter.acquire(
                key=self._client_key(scope),
                max_calls=self.max_calls,
                window_seconds=self.window_seconds,
            )
        except Exception as exc:
            # Fail-open, consistent with every other limiter here. Counted so
            # the unprotected window is visible instead of silent.
            http_rate_limit_degraded_total.inc()
            logger.error(
                "global_rate_limit_check_failed",
                path=scope.get("path", ""),
                error=str(exc),
            )
            return True

    async def _reject(self, scope: Scope, send: Send) -> None:
        """Answer 429 with the retry contract the frontend already handles."""
        path = scope.get("path", "")
        logger.warning(
            "global_rate_limit_exceeded",
            path=path,
            method=scope.get("method", ""),
            max_calls=self.max_calls,
            window_seconds=self.window_seconds,
        )
        # `endpoint_type="global"` keeps this counter's cardinality bounded: the
        # raw path is attacker-chosen, and one label value per URL is how a
        # metric takes down the Prometheus meant to watch it.
        http_rate_limit_hits_total.labels(endpoint="global", endpoint_type="global").inc()

        async def _no_body() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        response = JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please slow down and try again.",
                "retry_after": self.window_seconds,
            },
            headers={"Retry-After": str(self.window_seconds)},
        )
        await response(scope, _no_body, send)


class BodySizeLimitMiddleware:
    """Pure-ASGI middleware bounding the size of any request body (SEC-031).

    Endpoints validated their payload *after* materialising it — ``await
    request.body()`` on the Telegram and telephony webhooks, ``await
    file.read()`` on attachments and skill imports, the health-metrics batch —
    so the peak memory of a request was set by the client, not by us. Concurrent
    oversized POSTs therefore cost N × body before a single check ran, and on
    the webhooks that happened before authentication.

    Two complementary checks, in the order that matters:

    1. ``Content-Length``, when present and over the ceiling, is refused before
       the body is even requested. This is an optimisation, never the guarantee:
       the header is client-supplied and may be absent, understated, or replaced
       by chunked transfer encoding.
    2. The bytes actually delivered are counted as the handler consumes them.
       Crossing the ceiling ends the stream with an error, so an oversized body
       costs at most one chunk beyond the limit whatever the header claimed.

    The ceiling is a memory bound, not a business rule: per-endpoint limits are
    stricter and stay exactly where they are. This only removes the ability to
    choose how much of our RAM a request occupies.

    Streaming responses (SSE) are unaffected — only the request direction is
    wrapped. Non-HTTP scopes (WebSocket, lifespan) pass straight through.

    Known limit, inherited rather than introduced: ``CORSMiddleware`` is the
    innermost middleware, so it only decorates responses produced by the ROUTES.
    A 413 emitted from here therefore carries no ``Access-Control-Allow-Origin``,
    and a browser on the cross-origin frontend (``lia-back`` vs ``lia``) reports
    a network error instead of the status. ``ErrorHandlerMiddleware`` has the
    same property for its 500s. It stays acceptable because this ceiling only
    fires ABOVE every legitimate upload: a file over its own endpoint's limit is
    rejected by that endpoint, inside CORS, with a proper message. Reaching this
    guard means a body larger than anything the product accepts.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.max_bytes = settings.max_request_body_bytes
        self.exempt_paths = MAX_REQUEST_BODY_EXEMPT_PATHS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_exempt(scope):
            await self.app(scope, receive, send)
            return

        declared = self._oversized_declared_length(scope)
        if declared is not None:
            await self._reject(scope, send, declared_bytes=declared)
            return

        await self._run_bounded(scope, receive, send)

    def _is_exempt(self, scope: Scope) -> bool:
        """Whether this path opted out of the ceiling.

        Exact match, for the same reason as the global limiter above: a prefix
        test turns one exempted route into an exempted namespace. The list is
        empty today, so this changes no behaviour — it removes the trap that
        the first entry added to it would otherwise spring.
        """
        return scope.get("path", "") in self.exempt_paths

    def _oversized_declared_length(self, scope: Scope) -> int | None:
        """Return the declared body length when it already exceeds the ceiling.

        Reading the header lets an oversized request be refused without pulling
        a single byte from the stream. It is an optimisation, never the
        guarantee: the value is client-supplied and may be absent, understated,
        or replaced by chunked transfer encoding.

        Args:
            scope: ASGI HTTP scope.

        Returns:
            The declared length when it is over the ceiling, else ``None``.
        """
        raw = Headers(scope=scope).get("content-length")
        if raw is None:
            return None

        # A malformed Content-Length is a client or proxy quirk, not an attack
        # signal. Rejecting on it would turn any such quirk into a 413, so the
        # guard degrades to the byte counter — which enforces the real limit.
        with suppress(ValueError):
            declared = int(raw)
            if declared > self.max_bytes:
                return declared
        return None

    async def _run_bounded(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the app while counting the bytes it is allowed to consume."""
        state = {"received": 0, "limit_hit": False, "response_started": False}

        async def receive_bounded() -> Message:
            """Count what the client actually sends and stop at the ceiling."""
            message = await receive()
            if message["type"] != "http.request":
                return message

            state["received"] += len(message.get("body", b""))
            if state["received"] > self.max_bytes:
                state["limit_hit"] = True
                logger.warning(
                    "request_body_limit_exceeded",
                    path=scope.get("path", ""),
                    method=scope.get("method", ""),
                    received_bytes=state["received"],
                    max_bytes=self.max_bytes,
                )
                http_request_body_rejected_total.labels(reason="streamed_bytes").inc()
                # Report a disconnect so the handler's read unwinds instead of
                # waiting for bytes we will never deliver. Starlette turns this
                # into `ClientDisconnect`; the 413 below is what the client
                # actually receives, because `send_guarded` suppresses whatever
                # the unwinding handler tries to emit.
                return {"type": "http.disconnect"}
            return message

        async def send_guarded(message: Message) -> None:
            """Drop handler output once we have answered 413 ourselves."""
            if state["limit_hit"]:
                return
            if message["type"] == "http.response.start":
                state["response_started"] = True
            await send(message)

        try:
            await self.app(scope, receive_bounded, send_guarded)
        except Exception:
            # A handler unwinding on the synthetic disconnect must not surface
            # as a 500: the request was refused on purpose. Any other failure is
            # re-raised untouched for the error handler above us.
            if not state["limit_hit"]:
                raise

        if state["limit_hit"] and not state["response_started"]:
            await self._send_413(scope, send)

    async def _reject(self, scope: Scope, send: Send, *, declared_bytes: int) -> None:
        """Answer 413 on the declared length, without touching the body."""
        logger.warning(
            "request_body_too_large_declared",
            path=scope.get("path", ""),
            method=scope.get("method", ""),
            declared_bytes=declared_bytes,
            max_bytes=self.max_bytes,
        )
        http_request_body_rejected_total.labels(reason="declared_length").inc()
        await self._send_413(scope, send)

    @staticmethod
    async def _send_413(scope: Scope, send: Send) -> None:
        """Emit the 413 without consuming the request stream.

        The response is sent with a receive callable that reports an immediately
        empty body: `JSONResponse.__call__` never reads it, and supplying the
        real one would pull the very bytes this guard exists to avoid buffering.
        """

        async def _no_body() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
        await response(scope, _no_body, send)


class SecurityHeadersMiddleware:
    """
    Pure-ASGI middleware adding security headers to all responses.

    Headers added:
    - X-Frame-Options: DENY - Prevents clickjacking attacks
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-XSS-Protection: 1; mode=block - Enables XSS filter in legacy browsers
    - Strict-Transport-Security - Forces HTTPS for `HSTS_MAX_AGE` seconds
      (production only, same staged value as the web app — SEC-025)
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
                # HSTS, production only (SEC-025).
                #
                # This header used to be `max-age=31536000; includeSubDomains;
                # preload` — hardcoded, and in direct contradiction with the
                # policy the project had written down for the web app: both
                # directives are deliberately NOT emitted there because they are
                # near-irreversible, and `includeSubDomains` must not ship before
                # an inventory proves every subdomain is durably HTTPS. The
                # browser honours the header on API responses just as it does on
                # documents, so the stricter, undecided posture was the one
                # actually being served.
                #
                # Both surfaces now read the SAME ladder (`HSTS_MAX_AGE`), which
                # is what makes the staged rollout meaningful: a step is a
                # restart, and neither side can advance without the other.
                # Removing the directives does not retract pins already stored by
                # browsers — those expire on their own — it stops adding more.
                if settings.is_production and settings.hsts_max_age > 0:
                    headers["Strict-Transport-Security"] = f"max-age={settings.hsts_max_age}"
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
        # Same chokepoint as the rate limiter: GeoIP must enrich the REAL caller.
        # Reading the uvicorn-resolved peer let a scanner declaring itself as
        # loopback be recorded as `geo_country=local` — all 2600 rate-limit
        # warnings of the 2026-07-30 scan carry that value.
        resolved_ip = resolve_client_ip(scope)
        client_host: str | None = None if resolved_ip == UNKNOWN_CLIENT_IP else resolved_ip

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
            # Set only by the native shells, and only on their own requests
            # (ADR-246). A custom header forces a CORS preflight, which is why
            # this is worth stating: browsers send none of these and pay
            # nothing, while a shell pays one OPTIONS per method and path every
            # ten minutes — Starlette's default `max_age`. The alternative was a
            # list of OAuth paths in the web client, and a path allowlist rots.
            NATIVE_CLIENT_HEADER,
        ],
        expose_headers=["X-Request-ID"],
    )

    # Custom middleware (order matters - applied in reverse: the LAST added runs
    # FIRST). Effective order: RequestID → SecurityHeaders → Logging →
    # BodySizeLimit → ErrorHandler → routes.
    #
    # BodySizeLimit sits directly above the routes so it is the last thing a
    # request crosses before a handler can read its body — nothing between them
    # can consume the stream unbounded. It stays BELOW RequestID and Logging so
    # a rejected request keeps its correlation id and is still logged like any
    # other, and below SecurityHeaders so the 413 carries them too.
    #
    # RateLimit runs just ABOVE BodySizeLimit: a client over its budget is
    # refused before we spend anything reading its body, which is the cheaper
    # rejection of the two. Both stay under Logging so every refusal is
    # observable.
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    logger.info(
        "middleware_configured",
        cors_origins=settings.cors_origins,
    )
